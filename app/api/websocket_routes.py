import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_ws_token
from app.db.session import async_session_factory
from app.models.call import Call
from app.models.call_participant import CallParticipant

router = APIRouter(tags=["websocket"])

active_connections: dict[str, dict[str, WebSocket]] = {}


def _call_key(call_id: uuid.UUID) -> str:
    return str(call_id)


def _user_key(user_id: uuid.UUID) -> str:
    return str(user_id)


async def _broadcast_to_call_ws(
    call_id: uuid.UUID,
    event_type: str,
    data: dict,
    exclude_user: uuid.UUID | None = None,
):
    ck = _call_key(call_id)
    if ck not in active_connections:
        return

    payload = json.dumps(
        {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        default=str,
    )

    disconnected = []
    for uk, ws in active_connections[ck].items():
        if exclude_user and uk == _user_key(exclude_user):
            continue
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(uk)

    for uk in disconnected:
        active_connections[ck].pop(uk, None)


async def close_all_connections():
    for ck in list(active_connections.keys()):
        for uk, ws in list(active_connections[ck].items()):
            try:
                await ws.close(code=1001, reason="Server shutdown")
            except Exception:
                pass
        active_connections[ck].clear()
    active_connections.clear()


async def close_connection_for_user(call_id: uuid.UUID, user_id: uuid.UUID):
    ck = _call_key(call_id)
    uk = _user_key(user_id)
    if ck in active_connections and uk in active_connections[ck]:
        ws = active_connections[ck].pop(uk)
        try:
            await ws.close(code=4004, reason="Rimosso dalla chiamata")
        except Exception:
            pass


async def close_all_for_call(call_id: uuid.UUID):
    ck = _call_key(call_id)
    if ck not in active_connections:
        return
    for uk, ws in list(active_connections[ck].items()):
        try:
            await ws.close(code=4005, reason="Chiamata terminata")
        except Exception:
            pass
    active_connections.pop(ck, None)


@router.websocket("/api/v1/ws/call/{call_id}")
async def websocket_call_chat(websocket: WebSocket, call_id: uuid.UUID):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Token mancante")
        return

    user = decode_ws_token(token)
    if user is None:
        await websocket.close(code=4001, reason="Token non valido")
        return

    async with async_session_factory() as db:
        call_result = await db.execute(
            select(Call).where(Call.id == call_id, Call.is_active.is_(True))
        )
        if call_result.scalar_one_or_none() is None:
            await websocket.close(code=4002, reason="Chiamata non trovata o non attiva")
            return

        participant_result = await db.execute(
            select(CallParticipant).where(
                CallParticipant.call_id == call_id,
                CallParticipant.user_id == user.user_id,
                CallParticipant.left_at.is_(None),
            )
        )
        if participant_result.scalar_one_or_none() is None:
            await websocket.close(code=4003, reason="Non sei un partecipante di questa chiamata")
            return

    await websocket.accept()

    ck = _call_key(call_id)
    uk = _user_key(user.user_id)

    if ck not in active_connections:
        active_connections[ck] = {}
    active_connections[ck][uk] = websocket

    await _broadcast_to_call_ws(
        call_id,
        "user_online",
        {"user_id": str(user.user_id), "username": user.username},
        exclude_user=user.user_id,
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "data": {"message": "JSON non valido"},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )
                continue

            action = data.get("action")
            msg_type = data.get("type")

            # Support frontend format: { type: "chat_message", payload: { text: "..." } }
            if msg_type == "chat_message":
                payload = data.get("payload", {})
                content = payload.get("text", "").strip()
                if not content:
                    continue

                msg_out = {
                    "type": "chat_message",
                    "payload": {
                        "username": user.username,
                        "text": content,
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                payload_str = json.dumps(msg_out, default=str)
                # Broadcast to all EXCEPT sender (frontend adds message optimistically)
                ck2 = _call_key(call_id)
                if ck2 in active_connections:
                    disconnected = []
                    for uk2, ws2 in active_connections[ck2].items():
                        if uk2 == _user_key(user.user_id):
                            continue
                        try:
                            await ws2.send_text(payload_str)
                        except Exception:
                            disconnected.append(uk2)
                    for uk2 in disconnected:
                        active_connections[ck2].pop(uk2, None)

            elif action == "send_message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                msg_data = {
                    "type": "chat_message",
                    "payload": {
                        "username": user.username,
                        "text": content,
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                payload_str = json.dumps(msg_data, default=str)
                ck2 = _call_key(call_id)
                if ck2 in active_connections:
                    disconnected = []
                    for uk2, ws2 in active_connections[ck2].items():
                        if uk2 == _user_key(user.user_id):
                            continue
                        try:
                            await ws2.send_text(payload_str)
                        except Exception:
                            disconnected.append(uk2)
                    for uk2 in disconnected:
                        active_connections[ck2].pop(uk2, None)

            elif action == "typing" or msg_type == "typing":
                await _broadcast_to_call_ws(
                    call_id,
                    "typing",
                    {"user_id": str(user.user_id), "username": user.username},
                    exclude_user=user.user_id,
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if ck in active_connections:
            active_connections[ck].pop(uk, None)
            if not active_connections[ck]:
                del active_connections[ck]

        await _broadcast_to_call_ws(
            call_id,
            "user_offline",
            {"user_id": str(user.user_id), "username": user.username},
        )
