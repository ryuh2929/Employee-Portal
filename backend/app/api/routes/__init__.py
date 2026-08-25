from app.api.routes.admin_employees import router as admin_employees_router
from app.api.routes.auth import router as auth_router
from app.api.routes.background_checks import router as background_checks_router
from app.api.routes.employees import router as employees_router
from app.api.routes.health import router as health_router

__all__ = [
    "admin_employees_router",
    "auth_router",
    "background_checks_router",
    "employees_router",
    "health_router",
]
