import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuthContext, get_current_employee, require_csrf
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.core.security import DUMMY_PASSWORD_HASH, PASSWORD_HASH, generate_token, hash_token
from app.models import AuthSession, Employee, EmployeeStatus
from app.schemas import CsrfTokenResponse, EmployeeAuthResponse, LoginRequest


router = APIRouter(prefix="/auth", tags=["authentication"])


def set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=False,
        secure=settings.use_secure_cookies,
        samesite=settings.cookie_samesite,
        path="/",
    )


def validate_double_submit_csrf(request: Request, settings: Settings) -> None:
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("X-CSRF-Token")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        )


@router.get("/csrf", response_model=CsrfTokenResponse)
async def issue_csrf_token(response: Response) -> CsrfTokenResponse:
    settings = get_settings()
    token = generate_token()
    set_csrf_cookie(response, token, settings)
    return CsrfTokenResponse(csrf_token=token)


@router.post("/login", response_model=EmployeeAuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> Employee:
    settings = get_settings()
    validate_double_submit_csrf(request, settings)

    email = payload.email.strip().lower()
    result = await db.execute(select(Employee).where(Employee.email == email))
    employee = result.scalar_one_or_none()
    password_hash = employee.password_hash if employee else DUMMY_PASSWORD_HASH
    password_valid = PASSWORD_HASH.verify(payload.password, password_hash)
    if (
        employee is None
        or not password_valid
        or employee.status is not EmployeeStatus.ACTIVE
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    session_token = generate_token()
    csrf_token = generate_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.session_ttl_hours
    )
    db.add(
        AuthSession(
            employee_id=employee.id,
            token_hash=hash_token(session_token),
            csrf_token_hash=hash_token(csrf_token),
            expires_at=expires_at,
        )
    )
    await db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.use_secure_cookies,
        samesite=settings.cookie_samesite,
        path="/",
    )
    set_csrf_cookie(response, csrf_token, settings)
    return employee


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    settings = get_settings()
    auth.session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.use_secure_cookies,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=settings.use_secure_cookies,
        httponly=False,
        samesite=settings.cookie_samesite,
    )


@router.get("/me", response_model=EmployeeAuthResponse)
async def current_employee(
    employee: Employee = Depends(get_current_employee),
) -> Employee:
    return employee
