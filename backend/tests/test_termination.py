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
from app.models import AuthSession, Employee, EmployeeRole, EmployeeStatus


PREFIX = "TERMINATE-API-"
TARGET_PASSWORD = "Terminated-Login-Password-2026!"


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def termination_context() -> AsyncIterator[dict[str, object]]:
    await engine.dispose(close=False)
    async with SessionFactory() as session:
        await session.execute(delete(Employee).where(Employee.employee_number.like(f"{PREFIX}%")))
        admin = Employee(
            employee_number=f"{PREFIX}ADMIN", full_name="퇴사처리관리자",
            date_of_birth=date(1984, 1, 1), email="terminate-admin@example.com",
            password_hash=PASSWORD_HASH.hash("admin-password"), role=EmployeeRole.ADMIN,
        )
        actor = Employee(
            employee_number=f"{PREFIX}ACTOR", full_name="일반처리시도자",
            date_of_birth=date(1991, 2, 2), email="terminate-actor@example.com",
            password_hash=PASSWORD_HASH.hash("actor-password"),
        )
        target = Employee(
            employee_number=f"{PREFIX}TARGET", full_name="퇴사대상직원",
            date_of_birth=date(1993, 3, 3), email="terminate-target@example.com",
            password_hash=PASSWORD_HASH.hash(TARGET_PASSWORD),
        )
        session.add_all([admin, actor, target])
        await session.commit()
        for account in (admin, actor, target):
            await session.refresh(account)

        tokens: dict[str, list[tuple[str, str]]] = {}
        for name, account, count in (("admin", admin, 1), ("actor", actor, 1), ("target", target, 2)):
            tokens[name] = []
            for _ in range(count):
                session_token, csrf_token = generate_token(), generate_token()
                tokens[name].append((session_token, csrf_token))
                session.add(AuthSession(
                    employee_id=account.id, token_hash=hash_token(session_token),
                    csrf_token_hash=hash_token(csrf_token),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                ))
        await session.commit()

    yield {"admin": admin, "actor": actor, "target": target, "tokens": tokens}

    async with SessionFactory() as session:
        ids = list(await session.scalars(select(Employee.id).where(Employee.employee_number.like(f"{PREFIX}%"))))
        if ids:
            await session.execute(delete(AuthSession).where(AuthSession.employee_id.in_(ids)))
            await session.execute(delete(Employee).where(Employee.id.in_(ids)))
            await session.commit()


def authenticated_client(context: dict[str, object], account: str, device: int = 0) -> httpx.AsyncClient:
    settings = get_settings()
    tokens = context["tokens"]
    assert isinstance(tokens, dict)
    session_token, csrf_token = tokens[account][device]
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    client.cookies.set(settings.session_cookie_name, session_token)
    client.cookies.set(settings.csrf_cookie_name, csrf_token)
    return client


def csrf_header(context: dict[str, object], account: str) -> dict[str, str]:
    tokens = context["tokens"]
    assert isinstance(tokens, dict)
    return {"X-CSRF-Token": tokens[account][0][1]}


@pytest.mark.asyncio(loop_scope="module")
async def test_regular_employee_cannot_terminate_employee(
    termination_context: dict[str, object],
) -> None:
    target = termination_context["target"]
    assert isinstance(target, Employee)
    async with authenticated_client(termination_context, "actor") as client:
        response = await client.post(
            f"/admin/employees/{target.id}/terminate",
            headers=csrf_header(termination_context, "actor"),
        )
    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="module")
async def test_admin_terminates_employee_and_revokes_all_device_sessions(
    termination_context: dict[str, object],
) -> None:
    admin, target = termination_context["admin"], termination_context["target"]
    assert isinstance(admin, Employee) and isinstance(target, Employee)
    async with authenticated_client(termination_context, "admin") as client:
        response = await client.post(
            f"/admin/employees/{target.id}/terminate",
            headers=csrf_header(termination_context, "admin"),
        )
    assert response.status_code == 200
    assert response.json()["status"] == "TERMINATED"
    assert response.json()["terminated_by"] == str(admin.id)
    assert response.json()["terminated_at"] is not None

    async with SessionFactory() as session:
        stored = await session.get(Employee, target.id)
        sessions = list(await session.scalars(select(AuthSession).where(AuthSession.employee_id == target.id)))
    assert stored is not None
    assert stored.status is EmployeeStatus.TERMINATED
    assert stored.terminated_by == admin.id
    assert len(sessions) == 2
    assert all(item.revoked_at is not None for item in sessions)

    for device in (0, 1):
        async with authenticated_client(termination_context, "target", device) as client:
            assert (await client.get("/employees/me")).status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_terminated_employee_cannot_log_in(
    termination_context: dict[str, object],
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        csrf = (await client.get("/auth/csrf")).json()["csrf_token"]
        response = await client.post(
            "/auth/login",
            json={"email": "terminate-target@example.com", "password": TARGET_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_duplicate_termination_is_idempotent_and_preserves_audit_fields(
    termination_context: dict[str, object],
) -> None:
    admin, target = termination_context["admin"], termination_context["target"]
    assert isinstance(admin, Employee) and isinstance(target, Employee)
    async with SessionFactory() as session:
        before = await session.get(Employee, target.id)
        assert before is not None
        original_at, original_by = before.terminated_at, before.terminated_by

    async with authenticated_client(termination_context, "admin") as client:
        response = await client.post(
            f"/admin/employees/{target.id}/terminate",
            headers=csrf_header(termination_context, "admin"),
        )
    assert response.status_code == 200

    async with SessionFactory() as session:
        after = await session.get(Employee, target.id)
    assert after is not None
    assert after.terminated_at == original_at
    assert after.terminated_by == original_by
