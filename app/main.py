import logging
import sys
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

from app.api import calls, health, websocket_routes
from app.db.session import engine
from app.services.gateway_client import close_gateway_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== CALL SERVICE STARTUP BEGIN ===")
    logger.info("Call service ready")
    logger.info("=== CALL SERVICE STARTUP COMPLETE ===")

    yield

    await websocket_routes.close_all_connections()
    await close_gateway_client()
    await engine.dispose()


app = FastAPI(
    title="Call Service - Microservizio",
    description="Microservizio per la gestione delle chiamate audio/video con Jitsi Meet",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global catch-all: log EVERY unhandled 500 with full traceback ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(
        "[GLOBAL_ERROR] %s %s → %s: %s\n%s",
        request.method, request.url.path,
        type(exc).__name__, exc, tb,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )

app.include_router(health.router)
app.include_router(calls.router)
app.include_router(websocket_routes.router)
