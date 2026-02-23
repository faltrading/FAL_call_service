import time
import uuid

import jwt

from app.core.config import settings

JITSI_JWT_EXPIRY_SECONDS = 86400


def generate_jitsi_jwt(
    user_id: uuid.UUID,
    username: str,
    room_name: str,
    is_moderator: bool,
) -> str:
    now = int(time.time())

    payload = {
        "iss": settings.JITSI_APP_ID,
        "sub": settings.jitsi_domain,
        "aud": "jitsi",
        "room": room_name,
        "iat": now,
        "exp": now + JITSI_JWT_EXPIRY_SECONDS,
        "moderator": is_moderator,
        "context": {
            "user": {
                "id": str(user_id),
                "name": username,
                "moderator": is_moderator,
                "affiliation": "owner" if is_moderator else "member",
            },
        },
    }

    return jwt.encode(
        payload,
        settings.JITSI_APP_SECRET,
        algorithm="HS256",
        headers={"alg": "HS256", "typ": "JWT"},
    )


def build_jitsi_room_url(room_name: str, jitsi_jwt: str) -> str:
    base = settings.JITSI_URL.rstrip("/")
    return f"{base}/{room_name}?jwt={jitsi_jwt}"
