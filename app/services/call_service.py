import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AlreadyInCallError,
    CallNotActiveError,
    CallNotFoundError,
    InsufficientPermissionsError,
    NotAParticipantError,
)
from app.core.jitsi import get_jitsi_meeting_info
from app.models.call import Call
from app.models.call_participant import CallParticipant
from app.schemas.auth import CurrentUser
from app.services.realtime import realtime_service

logger = logging.getLogger(__name__)


def _generate_room_name() -> str:
    short_id = uuid.uuid4().hex[:12]
    return f"fal-{short_id}"


def _is_moderator(call: Call, user: CurrentUser) -> bool:
    return user.user_id == call.created_by or user.is_admin


async def create_call(
    db: AsyncSession,
    user: CurrentUser,
    room_name: str | None = None,
    max_participants: int | None = None,
) -> tuple[Call, CallParticipant, str, str, str, str]:
    """Returns (call, participant, jitsi_domain, jitsi_room, jitsi_jwt, jitsi_url)"""
    display_name = room_name.strip() if room_name else _generate_room_name()
    jitsi_room_id = _generate_room_name()
    logger.info(
        "[create_call_svc] display_name=%r jitsi_room_id=%s user_id=%s",
        display_name, jitsi_room_id, user.user_id,
    )

    try:
        call = Call(
            room_name=display_name,
            jitsi_room_id=jitsi_room_id,
            created_by=user.user_id,
            creator_username=user.username,
            max_participants=max_participants,
        )
        db.add(call)
        await db.flush()
        logger.info("[create_call_svc] Call flushed call_id=%s", call.id)
    except Exception as exc:
        logger.exception("[create_call_svc] DB flush FAILED: %s", exc)
        await db.rollback()
        raise

    try:
        participant = CallParticipant(
            call_id=call.id,
            user_id=user.user_id,
            username=user.username,
            role="moderator",
        )
        db.add(participant)
        await db.commit()
        await db.refresh(call)
        await db.refresh(participant)
        logger.info("[create_call_svc] DB commit OK participant_id=%s", participant.id)
    except Exception as exc:
        logger.exception("[create_call_svc] DB commit FAILED: %s", exc)
        await db.rollback()
        raise

    try:
        domain, jitsi_room, jwt_token, room_url = get_jitsi_meeting_info(
            user_id=user.user_id,
            username=user.username,
            room_name=jitsi_room_id,
            is_moderator=True,
        )
        logger.info(
            "[create_call_svc] Jitsi info OK domain=%s room=%s has_jwt=%s",
            domain, jitsi_room, bool(jwt_token),
        )
    except Exception as exc:
        logger.exception("[create_call_svc] get_jitsi_meeting_info FAILED: %s", exc)
        raise

    return call, participant, domain, jitsi_room, jwt_token, room_url


async def join_call(
    db: AsyncSession,
    call_id: uuid.UUID,
    user: CurrentUser,
) -> tuple[Call, CallParticipant, str, str, str, str]:
    """Returns (call, participant, jitsi_domain, jitsi_room, jitsi_jwt, jitsi_url)"""
    call = await _get_active_call(db, call_id)

    existing_result = await db.execute(
        select(CallParticipant).where(
            CallParticipant.call_id == call_id,
            CallParticipant.user_id == user.user_id,
            CallParticipant.left_at.is_(None),
        )
    )
    existing_participant = existing_result.scalar_one_or_none()

    is_mod = _is_moderator(call, user)
    role = "moderator" if is_mod else "participant"

    if existing_participant is not None:
        # Already in call — rejoin (return existing participation)
        participant = existing_participant
    else:
        try:
            participant = CallParticipant(
                call_id=call.id,
                user_id=user.user_id,
                username=user.username,
                role=role,
            )
            db.add(participant)
            await db.commit()
            await db.refresh(participant)
        except Exception:
            # Unique constraint race: another concurrent join may have inserted first
            await db.rollback()
            retry = await db.execute(
                select(CallParticipant).where(
                    CallParticipant.call_id == call_id,
                    CallParticipant.user_id == user.user_id,
                    CallParticipant.left_at.is_(None),
                )
            )
            participant = retry.scalar_one_or_none()
            if participant is None:
                raise

    jitsi_room_id = call.jitsi_room_id or call.room_name
    domain, jitsi_room, jwt_token, room_url = get_jitsi_meeting_info(
        user_id=user.user_id,
        username=user.username,
        room_name=jitsi_room_id,
        is_moderator=is_mod,
    )

    await realtime_service.broadcast_user_joined_call(
        call.id,
        {"user_id": user.user_id, "username": user.username, "role": role, "call_id": call.id},
    )

    return call, participant, domain, jitsi_room, jwt_token, room_url


async def leave_call(
    db: AsyncSession,
    call_id: uuid.UUID,
    user: CurrentUser,
) -> None:
    await _get_active_call(db, call_id)

    result = await db.execute(
        select(CallParticipant).where(
            CallParticipant.call_id == call_id,
            CallParticipant.user_id == user.user_id,
            CallParticipant.left_at.is_(None),
        )
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        raise NotAParticipantError()

    participant.left_at = datetime.now(timezone.utc)
    await db.commit()

    await realtime_service.broadcast_user_left_call(
        call_id,
        {"user_id": user.user_id, "username": user.username, "call_id": call_id},
    )


async def end_call(
    db: AsyncSession,
    call_id: uuid.UUID,
    user: CurrentUser,
) -> Call:
    call = await _get_active_call(db, call_id)

    if not _is_moderator(call, user):
        raise InsufficientPermissionsError()

    now = datetime.now(timezone.utc)
    call.is_active = False
    call.ended_at = now
    call.updated_at = now

    active_participants = await db.execute(
        select(CallParticipant).where(
            CallParticipant.call_id == call_id,
            CallParticipant.left_at.is_(None),
        )
    )
    for p in active_participants.scalars().all():
        p.left_at = now

    await db.commit()
    await db.refresh(call)

    await realtime_service.broadcast_call_ended(
        call.id,
        {"call_id": call.id, "ended_by": user.username},
    )

    return call


async def kick_participant(
    db: AsyncSession,
    call_id: uuid.UUID,
    target_user_id: uuid.UUID,
    user: CurrentUser,
) -> None:
    call = await _get_active_call(db, call_id)

    if not _is_moderator(call, user):
        raise InsufficientPermissionsError()

    result = await db.execute(
        select(CallParticipant).where(
            CallParticipant.call_id == call_id,
            CallParticipant.user_id == target_user_id,
            CallParticipant.left_at.is_(None),
        )
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        raise NotAParticipantError()

    participant.left_at = datetime.now(timezone.utc)
    participant.kicked = True
    await db.commit()

    await realtime_service.broadcast_user_kicked(
        call_id,
        {
            "user_id": target_user_id,
            "username": participant.username,
            "kicked_by": user.username,
            "call_id": call_id,
        },
    )


async def get_call(db: AsyncSession, call_id: uuid.UUID) -> Call:
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if call is None:
        raise CallNotFoundError()
    return call


async def get_active_calls(db: AsyncSession) -> list[Call]:
    result = await db.execute(
        select(Call).where(Call.is_active.is_(True)).order_by(Call.created_at.desc())
    )
    return list(result.scalars().all())


async def get_active_participant_count(db: AsyncSession, call_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(CallParticipant)
        .where(
            CallParticipant.call_id == call_id,
            CallParticipant.left_at.is_(None),
        )
    )
    return result.scalar() or 0


async def get_call_participants(db: AsyncSession, call_id: uuid.UUID) -> list[CallParticipant]:
    result = await db.execute(
        select(CallParticipant)
        .where(
            CallParticipant.call_id == call_id,
            CallParticipant.left_at.is_(None),
        )
        .order_by(CallParticipant.joined_at)
    )
    return list(result.scalars().all())


async def _get_active_call(db: AsyncSession, call_id: uuid.UUID) -> Call:
    call = await get_call(db, call_id)
    if not call.is_active:
        raise CallNotActiveError()
    return call
