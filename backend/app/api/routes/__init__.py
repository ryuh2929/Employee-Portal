from app.api.routes.auth import router as auth_router
from app.api.routes.employees import router as employees_router
from app.api.routes.health import router as health_router

__all__ = ["auth_router", "employees_router", "health_router"]
