import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(health.router)
app.include_router(calls.router)
app.include_router(websocket_routes.router)
