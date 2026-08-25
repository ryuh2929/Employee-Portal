from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import SessionFactory, engine
from app.core.security import PASSWORD_HASH, generate_token, hash_token
from app.main import app
from app.models import AuthSession, Employee, EmployeeRole


TEST_PREFIX = "ADMIN-API-"
CREATE_PAYLOAD = {
    "employee_number": "ADMIN-API-NEW",
    "full_name": "신규직원",
    "date_of_birth": "1997-05-06",
    "email": "admin-api-new@example.com",
    "phone": "010-3333-4444",
    "address": "서울특별시 종로구",
    "initial_password": "x",
}


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def admin_api_context() -> AsyncIterator[dict[str, object]]:
    await engine.dispose(close=False)
    async with SessionFactory() as session:
        await session.execute(delete(Employee).where(Employee.employee_number.like(f"{TEST_PREFIX}%")))
        admin = Employee(
            employee_number=f"{TEST_PREFIX}ADMIN",
            full_name="API관리자",
            date_of_birth=date(1985, 1, 2),
            email="admin-api-admin@example.com",
            password_hash=PASSWORD_HASH.hash("test-password"),
            role=EmployeeRole.ADMIN,
        )
        employee = Employee(
            employee_number=f"{TEST_PREFIX}EMPLOYEE",
            full_name="API일반직원",
            date_of_birth=date(1992, 3, 4),
            email="admin-api-employee@example.com",
            password_hash=PASSWORD_HASH.hash("test-password"),
        )
        session.add_all([admin, employee])
        await session.commit()
        await session.refresh(admin)
        await session.refresh(employee)

        tokens: dict[str, tuple[str, str]] = {}
        for name, account in (("admin", admin), ("employee", employee)):
            session_token, csrf_token = generate_token(), generate_token()
            tokens[name] = (session_token, csrf_token)
            session.add(
                AuthSession(
                    employee_id=account.id,
                    token_hash=hash_token(session_token),
                    csrf_token_hash=hash_token(csrf_token),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
        await session.commit()

    yield {"admin": admin, "employee": employee, "tokens": tokens}

    async with SessionFactory() as session:
        ids = list(
            await session.scalars(
                select(Employee.id).where(Employee.employee_number.like(f"{TEST_PREFIX}%"))
            )
        )
        if ids:
            await session.execute(delete(AuthSession).where(AuthSession.employee_id.in_(ids)))
            await session.execute(delete(Employee).where(Employee.id.in_(ids)))
            await session.commit()


def client_for(context: dict[str, object], account: str) -> httpx.AsyncClient:
    settings = get_settings()
    tokens = context["tokens"]
    assert isinstance(tokens, dict)
    session_token, csrf_token = tokens[account]
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )
    client.cookies.set(settings.session_cookie_name, session_token)
    client.cookies.set(settings.csrf_cookie_name, csrf_token)
    return client


def csrf_header(context: dict[str, object], account: str = "admin") -> dict[str, str]:
    tokens = context["tokens"]
    assert isinstance(tokens, dict)
    return {"X-CSRF-Token": tokens[account][1]}


@pytest.mark.asyncio(loop_scope="module")
async def test_admin_lists_searches_and_gets_employee_detail(
    admin_api_context: dict[str, object],
) -> None:
    async with client_for(admin_api_context, "admin") as client:
        listing = await client.get("/admin/employees", params={"search": "API일반"})
        assert listing.status_code == 200
        assert [item["employee_number"] for item in listing.json()] == [f"{TEST_PREFIX}EMPLOYEE"]
        assert "date_of_birth" not in listing.json()[0]

        employee = admin_api_context["employee"]
        assert isinstance(employee, Employee)
        detail = await client.get(f"/admin/employees/{employee.id}")
        assert detail.status_code == 200
        assert detail.json()["date_of_birth"] == "1992-03-04"
        assert "password_hash" not in detail.json()


@pytest.mark.asyncio(loop_scope="module")
async def test_admin_creates_employee_with_defaults_and_hashed_password(
    admin_api_context: dict[str, object],
) -> None:
    async with client_for(admin_api_context, "admin") as client:
        response = await client.post(
            "/admin/employees", json=CREATE_PAYLOAD, headers=csrf_header(admin_api_context)
        )
    assert response.status_code == 201
    assert response.json()["role"] == "EMPLOYEE"
    assert response.json()["status"] == "ACTIVE"

    async with SessionFactory() as session:
        created = await session.scalar(
            select(Employee).where(Employee.employee_number == CREATE_PAYLOAD["employee_number"])
        )
    assert created is not None
    assert created.password_hash != CREATE_PAYLOAD["initial_password"]
    assert created.password_hash.startswith("$argon2id$")
    assert PASSWORD_HASH.verify(CREATE_PAYLOAD["initial_password"], created.password_hash)


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("duplicate_field", ["employee_number", "email"])
async def test_duplicate_employee_number_or_email_is_rejected(
    admin_api_context: dict[str, object], duplicate_field: str
) -> None:
    payload = {
        **CREATE_PAYLOAD,
        "employee_number": f"{TEST_PREFIX}DUP-{duplicate_field}",
        "email": f"admin-api-dup-{duplicate_field}@example.com",
        duplicate_field: CREATE_PAYLOAD[duplicate_field],
    }
    async with client_for(admin_api_context, "admin") as client:
        response = await client.post(
            "/admin/employees", json=payload, headers=csrf_header(admin_api_context)
        )
    assert response.status_code == 409


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(
    ("field", "value"),
    [("email", "not-an-email"), ("employee_number", "bad number!"), ("full_name", "   "), ("date_of_birth", "2999-01-01")],
)
async def test_invalid_create_input_is_rejected(
    admin_api_context: dict[str, object], field: str, value: str
) -> None:
    payload = {**CREATE_PAYLOAD, "employee_number": f"{TEST_PREFIX}INVALID-{field}", "email": f"invalid-{field}@example.com", field: value}
    async with client_for(admin_api_context, "admin") as client:
        response = await client.post(
            "/admin/employees", json=payload, headers=csrf_header(admin_api_context)
        )
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="module")
async def test_admin_updates_allowed_fields_but_cannot_update_role_or_status(
    admin_api_context: dict[str, object],
) -> None:
    employee = admin_api_context["employee"]
    assert isinstance(employee, Employee)
    async with client_for(admin_api_context, "admin") as client:
        response = await client.patch(
            f"/admin/employees/{employee.id}",
            json={"full_name": "수정된직원", "phone": "010-7777-8888"},
            headers=csrf_header(admin_api_context),
        )
        assert response.status_code == 200
        assert response.json()["full_name"] == "수정된직원"

        for protected in ({"role": "ADMIN"}, {"status": "TERMINATED"}, {"initial_password": "New-Password!"}):
            blocked = await client.patch(
                f"/admin/employees/{employee.id}",
                json=protected,
                headers=csrf_header(admin_api_context),
            )
            assert blocked.status_code == 422


@pytest.mark.asyncio(loop_scope="module")
async def test_regular_employee_is_forbidden_from_every_admin_operation(
    admin_api_context: dict[str, object],
) -> None:
    employee = admin_api_context["employee"]
    assert isinstance(employee, Employee)
    headers = csrf_header(admin_api_context, "employee")
    async with client_for(admin_api_context, "employee") as client:
        responses = [
            await client.get("/admin/employees"),
            await client.get(f"/admin/employees/{employee.id}"),
            await client.post("/admin/employees", json=CREATE_PAYLOAD, headers=headers),
            await client.patch(f"/admin/employees/{employee.id}", json={"phone": "010"}, headers=headers),
        ]
    assert [response.status_code for response in responses] == [403, 403, 403, 403]
