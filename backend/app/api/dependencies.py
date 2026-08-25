import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.security import hash_token
from app.models import AuthSession, Employee, EmployeeRole, EmployeeStatus


@dataclass(frozen=True)
class AuthContext:
    employee: Employee
    session: AuthSession


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise authentication_error()

    result = await db.execute(
        select(AuthSession)
        .options(joinedload(AuthSession.employee))
        .where(AuthSession.token_hash == hash_token(token))
    )
    auth_session = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if (
        auth_session is None
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
    ):
        raise authentication_error()

    if auth_session.employee.status is not EmployeeStatus.ACTIVE:
        auth_session.revoked_at = now
        await db.commit()
        raise authentication_error()

    return AuthContext(employee=auth_session.employee, session=auth_session)


async def get_current_employee(
    auth: AuthContext = Depends(get_auth_context),
) -> Employee:
    return auth.employee


async def require_csrf(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    settings = get_settings()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("X-CSRF-Token")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not hmac.compare_digest(hash_token(header_token), auth.session.csrf_token_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )
    return auth


def require_roles(*allowed_roles: EmployeeRole) -> Callable[..., Employee]:
    async def role_dependency(
        employee: Employee = Depends(get_current_employee),
    ) -> Employee:
        if employee.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return employee

    return role_dependency


require_employee = require_roles(EmployeeRole.EMPLOYEE, EmployeeRole.ADMIN)
require_admin = require_roles(EmployeeRole.ADMIN)
