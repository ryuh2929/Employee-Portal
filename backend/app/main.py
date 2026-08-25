from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin_employees import router as admin_employees_router
from app.api.routes.auth import router as auth_router
from app.api.routes.background_checks import router as background_checks_router
from app.api.routes.employees import router as employees_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.database import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


settings = get_settings()

app = FastAPI(
    title="Employee Portal API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(employees_router)
app.include_router(admin_employees_router)
app.include_router(background_checks_router)
