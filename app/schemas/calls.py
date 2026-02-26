import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CallCreate(BaseModel):
    room_name: str | None = None
    max_participants: int | None = Field(default=None, ge=2)


class CallResponse(BaseModel):
    id: uuid.UUID
    room_name: str
    created_by: uuid.UUID
    creator_username: str
    is_active: bool
    status: str = "active"
    max_participants: int | None = None
    participant_count: int = 0
    started_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None

    class Config:
        from_attributes = True


class CallListResponse(BaseModel):
    calls: list[CallResponse]
    total: int


class CallParticipantResponse(BaseModel):
    id: uuid.UUID
    call_id: uuid.UUID | None = None
    user_id: uuid.UUID
    username: str
    role: str
    joined_at: datetime
    left_at: datetime | None = None

    class Config:
        from_attributes = True


class JoinCallResponse(BaseModel):
    call: CallResponse
    participant: CallParticipantResponse
    jitsi_jwt: str
    jitsi_room: str
    jitsi_domain: str
    jitsi_room_url: str = ""


class CreateCallResponse(BaseModel):
    call: CallResponse
    participant: CallParticipantResponse
    jitsi_jwt: str
    jitsi_room: str
    jitsi_domain: str
    jitsi_room_url: str = ""


class KickRequest(BaseModel):
    reason: str | None = None
