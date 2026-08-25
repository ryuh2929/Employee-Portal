from collections.abc import AsyncIterator
from datetime import date, datetime, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.dependencies import require_admin, require_employee
from app.core.config import Settings, get_settings
from app.core.database import SessionFactory
from app.core.security import PASSWORD_HASH, hash_token
from app.main import app
from app.models import AuthSession, Employee, EmployeeRole, EmployeeStatus


TEST_PASSWORD = "Authentication-Test-Password-2026!"
TEST_EMAILS = {
    "employee": "auth.employee@example.com",
    "admin": "auth.admin@example.com",
    "terminated": "auth.terminated@example.com",
}


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def auth_employees() -> AsyncIterator[dict[str, Employee]]:
    async with SessionFactory() as session:
        await session.execute(delete(Employee).where(Employee.email.in_(TEST_EMAILS.values())))
        password_hash = PASSWORD_HASH.hash(TEST_PASSWORD)
        employees = {
            "employee": Employee(
                employee_number="AUTH-E001",
                full_name="인증직원",
                date_of_birth=date(1993, 4, 5),
                email=TEST_EMAILS["employee"],
                password_hash=password_hash,
                role=EmployeeRole.EMPLOYEE,
            ),
            "admin": Employee(
                employee_number="AUTH-A001",
                full_name="인증관리자",
                date_of_birth=date(1988, 6, 7),
                email=TEST_EMAILS["admin"],
                password_hash=password_hash,
                role=EmployeeRole.ADMIN,
            ),
            "terminated": Employee(
                employee_number="AUTH-T001",
                full_name="퇴사직원",
                date_of_birth=date(1990, 8, 9),
                email=TEST_EMAILS["terminated"],
                password_hash=password_hash,
                status=EmployeeStatus.TERMINATED,
                terminated_at=datetime.now(timezone.utc),
            ),
        }
        session.add_all(employees.values())
        await session.commit()
        for employee in employees.values():
            await session.refresh(employee)

    yield employees

    ids = [employee.id for employee in employees.values()]
    async with SessionFactory() as session:
        await session.execute(delete(AuthSession).where(AuthSession.employee_id.in_(ids)))
        await session.execute(delete(Employee).where(Employee.id.in_(ids)))
        await session.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def client(auth_employees: dict[str, Employee]) -> AsyncIterator[httpx.AsyncClient]:
    del auth_employees
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as value:
        yield value


async def csrf_token(client: httpx.AsyncClient) -> str:
    response = await client.get("/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def login(
    client: httpx.AsyncClient,
    email: str,
    password: str = TEST_PASSWORD,
) -> httpx.Response:
    token = await csrf_token(client)
    return await client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": token},
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_successful_login_creates_hashed_server_session_and_me(
    client: httpx.AsyncClient,
) -> None:
    settings = get_settings()
    response = await login(client, TEST_EMAILS["employee"].upper())

    assert response.status_code == 200
    assert response.json()["email"] == TEST_EMAILS["employee"]
    assert "password_hash" not in response.json()
    cookie_headers = response.headers.get_list("set-cookie")
    session_header = next(
        value for value in cookie_headers if value.startswith(settings.session_cookie_name)
    )
    assert "HttpOnly" in session_header
    assert "SameSite=lax" in session_header
    assert "Secure" not in session_header

    raw_token = client.cookies[settings.session_cookie_name]
    async with SessionFactory() as session:
        stored = await session.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_token(raw_token))
        )
    assert stored is not None
    assert stored.token_hash != raw_token

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["employee_number"] == "AUTH-E001"


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    ("email", "password"),
    [
        (TEST_EMAILS["employee"], "wrong-password"),
        ("missing@example.com", TEST_PASSWORD),
    ],
)
async def test_invalid_credentials_are_rejected(
    client: httpx.AsyncClient,
    email: str,
    password: str,
) -> None:
    response = await login(client, email, password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


@pytest.mark.asyncio(loop_scope="module")
async def test_terminated_employee_cannot_log_in(client: httpx.AsyncClient) -> None:
    response = await login(client, TEST_EMAILS["terminated"])

    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_active_session_is_blocked_when_employee_becomes_terminated(
    client: httpx.AsyncClient,
    auth_employees: dict[str, Employee],
) -> None:
    response = await login(client, TEST_EMAILS["employee"])
    assert response.status_code == 200
    employee_id = auth_employees["employee"].id

    async with SessionFactory() as session:
        employee = await session.get(Employee, employee_id)
        assert employee is not None
        employee.status = EmployeeStatus.TERMINATED
        employee.terminated_at = datetime.now(timezone.utc)
        await session.commit()

    assert (await client.get("/auth/me")).status_code == 401

    async with SessionFactory() as session:
        employee = await session.get(Employee, employee_id)
        assert employee is not None
        employee.status = EmployeeStatus.ACTIVE
        employee.terminated_at = None
        await session.commit()


@pytest.mark.asyncio(loop_scope="module")
async def test_logout_requires_csrf_and_revokes_existing_session(
    client: httpx.AsyncClient,
) -> None:
    settings = get_settings()
    response = await login(client, TEST_EMAILS["admin"])
    assert response.status_code == 200
    raw_session = client.cookies[settings.session_cookie_name]

    missing_csrf = await client.post("/auth/logout")
    assert missing_csrf.status_code == 403

    csrf = client.cookies[settings.csrf_cookie_name]
    logout_response = await client.post(
        "/auth/logout", headers={"X-CSRF-Token": csrf}
    )
    assert logout_response.status_code == 204

    client.cookies.set(settings.session_cookie_name, raw_session)
    assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_login_requires_csrf(client: httpx.AsyncClient) -> None:
    client.cookies.clear()
    response = await client.post(
        "/auth/login",
        json={"email": TEST_EMAILS["employee"], "password": TEST_PASSWORD},
    )

    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="module")
async def test_employee_and_admin_role_dependencies(
    auth_employees: dict[str, Employee],
) -> None:
    employee = auth_employees["employee"]
    admin = auth_employees["admin"]

    assert await require_employee(employee) is employee
    assert await require_employee(admin) is admin
    assert await require_admin(admin) is admin
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(employee)
    assert exc_info.value.status_code == 403


def test_cookie_security_defaults_follow_environment() -> None:
    common = {"_env_file": None, "postgres_password": "test-password"}

    assert not Settings(app_env="development", **common).use_secure_cookies
    assert Settings(app_env="production", **common).use_secure_cookies
    assert Settings(
        app_env="development", cookie_samesite="none", **common
    ).use_secure_cookies
