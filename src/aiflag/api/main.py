from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aiflag.api.routers import demo, flags, quality, sdk, system
from aiflag.config import settings
from aiflag.workers.gates import gate_loop


@asynccontextmanager
async def lifespan(_app: FastAPI):
    stop = asyncio.Event()
    task = None
    if settings.gate_enabled:
        task = asyncio.create_task(gate_loop(stop))
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="Warden", description="AI feature flags with gradual rollout", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(flags.router)
app.include_router(quality.router)
app.include_router(demo.router)
app.include_router(sdk.router)
app.include_router(system.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "warden",
        "mock_llm": str(settings.demo_mock_llm).lower(),
    }
