import time
import uuid

import jwt

from app.core.config import settings

JITSI_JWT_EXPIRY_SECONDS = 86400


def _load_private_key() -> str:
    """Return PEM-formatted RSA private key from settings."""
    raw = settings.JITSI_APP_SECRET.strip()
    # Environment variables often store literal '\n' instead of real newlines
    if "\\n" in raw:
        raw = raw.replace("\\n", "\n")
    if raw.startswith("-----"):
        return raw
    # Raw base64 without PEM headers – wrap it
    lines = [raw[i : i + 64] for i in range(0, len(raw), 64)]
    return "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END RSA PRIVATE KEY-----"


def generate_jitsi_jwt(
    user_id: uuid.UUID,
    username: str,
    room_name: str,
    is_moderator: bool,
) -> str:
    now = int(time.time())

    payload = {
        "iss": "chat",
        "sub": settings.JITSI_APP_ID,
        "aud": "jitsi",
        "room": "*",
        "iat": now,
        "nbf": now,
        "exp": now + JITSI_JWT_EXPIRY_SECONDS,
        "context": {
            "user": {
                "id": str(user_id),
                "name": username,
                "moderator": "true" if is_moderator else "false",
                "avatar": "",
                "email": "",
            },
            "features": {
                "livestreaming": "false",
                "recording": "false",
                "transcription": "false",
                "outbound-call": "false",
            },
        },
    }

    kid = f"{settings.JITSI_APP_ID}/{settings.JITSI_API_KEY_ID}"

    return jwt.encode(
        payload,
        _load_private_key(),
        algorithm="RS256",
        headers={"alg": "RS256", "typ": "JWT", "kid": kid},
    )


def build_jitsi_room_url(room_name: str, jitsi_jwt: str) -> str:
    base = settings.JITSI_URL.rstrip("/")
    return f"{base}/{settings.JITSI_APP_ID}/{room_name}?jwt={jitsi_jwt}"
