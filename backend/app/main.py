import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_db
from app.api.ws import router as ws_router
from app.api.http import router as http_router
from app.services import monitor_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_paper()
    init_db()
    task = asyncio.create_task(monitor_service.run_monitor())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(ws_router)
app.include_router(http_router)
