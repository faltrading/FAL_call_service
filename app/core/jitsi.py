import logging
import time
import uuid

import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

JITSI_JWT_EXPIRY_SECONDS = 86400

# Default free public Jitsi instance
DEFAULT_JITSI_DOMAIN = "meet.jit.si"


def _has_jaas_config() -> bool:
    """Check if JaaS (Jitsi as a Service) credentials are configured."""
    return bool(
        settings.JITSI_APP_ID
        and settings.JITSI_APP_SECRET
        and settings.JITSI_URL
    )


def _load_private_key() -> str:
    """Return PEM-formatted RSA private key from settings."""
    raw = settings.JITSI_APP_SECRET.strip()
    if "\\n" in raw:
        raw = raw.replace("\\n", "\n")
    if raw.startswith("-----"):
        return raw
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


def get_jitsi_meeting_info(
    user_id: uuid.UUID,
    username: str,
    room_name: str,
    is_moderator: bool,
) -> tuple[str, str, str, str]:
    """
    Returns (domain, jitsi_room, jwt_token, room_url).

    If JaaS credentials are configured, uses JaaS with RS256 JWT.
    Otherwise falls back to the free public meet.jit.si (no JWT needed).
    """
    if _has_jaas_config():
        domain = settings.jitsi_domain
        jwt_token = generate_jitsi_jwt(user_id, username, room_name, is_moderator)
        jitsi_room = room_name
        room_url = build_jitsi_room_url(room_name, jwt_token)
        logger.info(f"JaaS mode: domain={domain}, room={jitsi_room}")
    else:
        domain = settings.jitsi_domain if settings.JITSI_URL else DEFAULT_JITSI_DOMAIN
        jwt_token = ""
        jitsi_room = room_name
        room_url = f"https://{domain}/{room_name}"
        logger.info(f"Free Jitsi mode: domain={domain}, room={jitsi_room}")

    return domain, jitsi_room, jwt_token, room_url
