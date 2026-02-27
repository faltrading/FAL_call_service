import uuid
from datetime import datetime

from supabase import create_client

from app.core.config import settings

_supabase_client = None


def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.SUPABASE_PROJECT_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_client


def _serialize(obj):
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _make_serializable(data: dict) -> dict:
    return {k: _serialize(v) for k, v in data.items()}


class RealtimeService:
    def _get_channel_name(self, call_id: uuid.UUID) -> str:
        return f"call:{call_id}"

    async def broadcast_to_call(self, call_id: uuid.UUID, event_type: str, payload: dict):
        client = get_supabase_client()
        channel_name = self._get_channel_name(call_id)
        serialized = _make_serializable(payload)

        try:
            channel = client.channel(channel_name)
            channel.subscribe()
            channel.send_broadcast(
                event=event_type,
                data=serialized,
            )
            channel.unsubscribe()
        except Exception:
            pass

    async def broadcast_user_joined_call(self, call_id: uuid.UUID, user_data: dict):
        await self.broadcast_to_call(call_id, "user_joined_call", user_data)

    async def broadcast_user_left_call(self, call_id: uuid.UUID, user_data: dict):
        await self.broadcast_to_call(call_id, "user_left_call", user_data)

    async def broadcast_call_ended(self, call_id: uuid.UUID, call_data: dict):
        await self.broadcast_to_call(call_id, "call_ended", call_data)

    async def broadcast_user_kicked(self, call_id: uuid.UUID, user_data: dict):
        await self.broadcast_to_call(call_id, "user_kicked", user_data)

    async def broadcast_call_deleted(self, call_id: uuid.UUID, call_data: dict):
        await self.broadcast_to_call(call_id, "call_deleted", call_data)


realtime_service = RealtimeService()
