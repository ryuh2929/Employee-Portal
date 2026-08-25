from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.core.security import generate_token, hash_token
from app.main import app
from app.models import AuthSession, Employee, EmployeeRole, EmployeeStatus


@pytest_asyncio.fixture(loop_scope="module")
async def self_service_employee() -> AsyncIterator[Employee]:
    email = "self.service@example.com"
    await engine.dispose(close=False)
    async with SessionFactory() as session:
        await session.execute(delete(Employee).where(Employee.email == email))
        employee = Employee(
            employee_number="SELF-E001",
            full_name="본인조회",
            date_of_birth=date(1994, 2, 3),
            email=email,
            password_hash="$argon2id$test",
            phone="010-0000-0000",
            address="서울특별시",
            role=EmployeeRole.EMPLOYEE,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)

    yield employee

    async with SessionFactory() as session:
        await session.execute(delete(AuthSession).where(AuthSession.employee_id == employee.id))
        await session.execute(delete(Employee).where(Employee.id == employee.id))
        await session.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def authenticated_client(
    self_service_employee: Employee,
) -> AsyncIterator[httpx.AsyncClient]:
    settings = get_settings()
    session_token = generate_token()
    csrf_token = generate_token()
    async with SessionFactory() as session:
        session.add(
            AuthSession(
                employee_id=self_service_employee.id,
                token_hash=hash_token(session_token),
                csrf_token_hash=hash_token(csrf_token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.set(settings.session_cookie_name, session_token)
        client.cookies.set(settings.csrf_cookie_name, csrf_token)
        yield client


@pytest.mark.asyncio(loop_scope="module")
async def test_employee_can_get_only_own_profile(
    authenticated_client: httpx.AsyncClient,
) -> None:
    response = await authenticated_client.get("/employees/me")

    assert response.status_code == 200
    assert response.json()["employee_number"] == "SELF-E001"
    assert "password_hash" not in response.json()


@pytest.mark.asyncio(loop_scope="module")
async def test_employee_can_update_phone_and_address(
    authenticated_client: httpx.AsyncClient,
) -> None:
    settings = get_settings()
    csrf = authenticated_client.cookies[settings.csrf_cookie_name]
    response = await authenticated_client.patch(
        "/employees/me",
        json={"phone": "010-1234-5678", "address": "부산광역시 해운대구"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "010-1234-5678"
    assert response.json()["address"] == "부산광역시 해운대구"


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    "field",
    ["employee_number", "full_name", "date_of_birth", "email", "role", "status"],
)
async def test_employee_cannot_update_protected_fields(
    authenticated_client: httpx.AsyncClient,
    field: str,
) -> None:
    settings = get_settings()
    csrf = authenticated_client.cookies[settings.csrf_cookie_name]
    response = await authenticated_client.patch(
        "/employees/me",
        json={field: "forbidden"},
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


@pytest.mark.asyncio(loop_scope="module")
async def test_self_service_requires_authentication() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        assert (await client.get("/employees/me")).status_code == 401
        assert (await client.patch("/employees/me", json={"phone": "010"})).status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_update_requires_csrf(authenticated_client: httpx.AsyncClient) -> None:
    response = await authenticated_client.patch(
        "/employees/me", json={"phone": "010-9999-9999"}
    )

    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="module")
async def test_expired_session_cannot_access_profile(
    self_service_employee: Employee,
) -> None:
    settings = get_settings()
    expired_token = generate_token()
    async with SessionFactory() as session:
        session.add(
            AuthSession(
                employee_id=self_service_employee.id,
                token_hash=hash_token(expired_token),
                csrf_token_hash=hash_token(generate_token()),
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        client.cookies.set(settings.session_cookie_name, expired_token)
        assert (await client.get("/employees/me")).status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_terminated_employee_session_cannot_access_profile(
    authenticated_client: httpx.AsyncClient,
    self_service_employee: Employee,
) -> None:
    async with SessionFactory() as session:
        employee = await session.get(Employee, self_service_employee.id)
        assert employee is not None
        employee.status = EmployeeStatus.TERMINATED
        employee.terminated_at = datetime.now(timezone.utc)
        await session.commit()

    assert (await authenticated_client.get("/employees/me")).status_code == 401

    async with SessionFactory() as session:
        employee = await session.get(Employee, self_service_employee.id)
        assert employee is not None
        employee.status = EmployeeStatus.ACTIVE
        employee.terminated_at = None
        await session.commit()
