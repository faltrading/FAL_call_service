import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.calls import (
    CallCreate,
    CallListResponse,
    CallParticipantResponse,
    CallResponse,
    CreateCallResponse,
    JoinCallResponse,
    KickRequest,
)
from app.services import call_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calls/rooms", tags=["calls"])


def _participant_response(p) -> CallParticipantResponse:
    return CallParticipantResponse(
        id=p.id,
        call_id=p.call_id,
        user_id=p.user_id,
        username=p.username,
        role=p.role,
        joined_at=p.joined_at,
        left_at=p.left_at,
    )


async def _build_call_response(db, call) -> CallResponse:
    count = await call_service.get_active_participant_count(db, call.id)
    return CallResponse(
        id=call.id,
        room_name=call.room_name,
        created_by=call.created_by,
        creator_username=call.creator_username,
        is_active=call.is_active,
        status="active" if call.is_active else "ended",
        max_participants=call.max_participants,
        participant_count=count,
        started_at=call.created_at,
        created_at=call.created_at,
        updated_at=call.updated_at,
        ended_at=call.ended_at,
    )


@router.post("", response_model=CreateCallResponse, status_code=201)
async def create_call(
    body: CallCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    logger.info(
        "[create_call] START user=%s user_id=%s room_name=%r max_participants=%s",
        current_user.username, current_user.user_id, body.room_name, body.max_participants,
    )
    try:
        call, participant, jitsi_domain, jitsi_room, jitsi_jwt, jitsi_url = (
            await call_service.create_call(
                db, current_user, body.room_name, body.max_participants
            )
        )
        logger.info(
            "[create_call] OK call_id=%s jitsi_domain=%s jitsi_room=%s",
            call.id, jitsi_domain, jitsi_room,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "[create_call] FAILED user=%s room_name=%r error=%s",
            current_user.username, body.room_name, exc,
        )
        raise HTTPException(status_code=500, detail=f"Internal error while creating call: {exc}") from exc

    try:
        call_response = await _build_call_response(db, call)
    except Exception as exc:
        logger.exception("[create_call] _build_call_response FAILED call_id=%s error=%s", call.id, exc)
        raise HTTPException(status_code=500, detail=f"Error building response: {exc}") from exc

    return CreateCallResponse(
        call=call_response,
        participant=_participant_response(participant),
        jitsi_jwt=jitsi_jwt,
        jitsi_room=jitsi_room,
        jitsi_domain=jitsi_domain,
        jitsi_room_url=jitsi_url,
    )


@router.get("", response_model=CallListResponse)
async def list_active_calls(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    logger.info("[list_active_calls] START user=%s", current_user.username)
    try:
        calls = await call_service.get_active_calls(db)
        logger.info("[list_active_calls] got %d calls from DB", len(calls))
        responses = [await _build_call_response(db, c) for c in calls]
        return CallListResponse(calls=responses, total=len(responses))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[list_active_calls] FAILED user=%s error=%s", current_user.username, exc)
        raise HTTPException(status_code=500, detail=f"Internal error listing calls: {exc}") from exc


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    call = await call_service.get_call(db, call_id)
    return await _build_call_response(db, call)


@router.get("/{call_id}/participants", response_model=list[CallParticipantResponse])
async def list_participants(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    participants = await call_service.get_call_participants(db, call_id)
    return [_participant_response(p) for p in participants]


@router.post("/{call_id}/join", response_model=JoinCallResponse)
async def join_call(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        call, participant, jitsi_domain, jitsi_room, jitsi_jwt, jitsi_url = (
            await call_service.join_call(db, call_id, current_user)
        )
    except Exception as exc:
        # Re-raise known HTTP exceptions; log and wrap anything else
        from fastapi import HTTPException
        if isinstance(exc, HTTPException):
            raise
        logger.exception("Unhandled error in join_call for call_id=%s user=%s", call_id, current_user.username)
        raise HTTPException(status_code=500, detail="Internal error while joining call") from exc

    call_response = await _build_call_response(db, call)
    return JoinCallResponse(
        call=call_response,
        participant=_participant_response(participant),
        jitsi_jwt=jitsi_jwt,
        jitsi_room=jitsi_room,
        jitsi_domain=jitsi_domain,
        jitsi_room_url=jitsi_url,
    )


@router.post("/{call_id}/leave", status_code=204)
async def leave_call(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await call_service.leave_call(db, call_id, current_user)


@router.post("/{call_id}/end", response_model=CallResponse)
async def end_call(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    call = await call_service.end_call(db, call_id, current_user)
    return await _build_call_response(db, call)


@router.delete("/{call_id}", status_code=204)
async def delete_call(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a call. Only the creator or an admin can do this."""
    await call_service.delete_call(db, call_id, current_user)


@router.delete("/{call_id}/participants/{user_id}/kick", status_code=204)
async def kick_participant(
    call_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await call_service.kick_participant(db, call_id, user_id, current_user)
