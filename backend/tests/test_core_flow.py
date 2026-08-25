from datetime import date, datetime, timezone

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.database import SessionFactory, engine
from app.core.security import PASSWORD_HASH
from app.main import app
from app.models import AuthSession, BackgroundCheckRequest, Employee, EmployeeRole
from app.services.background_checks import (
    ExternalBackgroundCheckCreated,
    ExternalBackgroundCheckList,
    ExternalBackgroundCheckResult,
    ExternalBackgroundCheckSummary,
    get_background_check_client,
)


PREFIX = "CORE-FLOW-"
ADMIN_PASSWORD = "Core-Admin-Password-2026!"
EMPLOYEE_PASSWORD = "Core-Employee-Password-2026!"


class CoreFlowBackgroundClient:
    async def create(self, **kwargs: str) -> ExternalBackgroundCheckCreated:
        return ExternalBackgroundCheckCreated(
            checkId="CHK-CORE-FLOW", employeeId=kwargs["employee_id"],
            status="pending", createdAt="2026-08-25T10:00:00Z",
        )

    async def list_for_employee(self, employee_id: str) -> ExternalBackgroundCheckList:
        return ExternalBackgroundCheckList(
            employeeId=employee_id,
            checks=[ExternalBackgroundCheckSummary(
                checkId="CHK-CORE-FLOW", status="clear",
                createdAt="2026-08-25T10:00:00Z", completedAt="2026-08-25T10:01:00Z",
            )], totalCount=1,
        )

    async def get(self, check_id: str) -> ExternalBackgroundCheckResult:
        return ExternalBackgroundCheckResult(
            checkId=check_id, employeeId=f"{PREFIX}EMPLOYEE",
            firstName="확정이름", lastName="확정성", dateOfBirth="1994-04-05",
            status="clear", criminalRecord=False, educationVerified=True,
            employmentVerified=True, creditScore="good",
            createdAt="2026-08-25T10:00:00Z", completedAt="2026-08-25T10:01:00Z",
        )


async def csrf(client: httpx.AsyncClient) -> str:
    response = await client.get("/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    token = await csrf(client)
    return await client.post(
        "/auth/login", json={"email": email, "password": password},
        headers={"X-CSRF-Token": token},
    )


@pytest.mark.asyncio
async def test_complete_employee_portal_core_flow() -> None:
    await engine.dispose(close=False)
    async with SessionFactory() as session:
        existing_ids = list(await session.scalars(select(Employee.id).where(Employee.employee_number.like(f"{PREFIX}%"))))
        if existing_ids:
            await session.execute(delete(BackgroundCheckRequest).where(BackgroundCheckRequest.employee_id.in_(existing_ids)))
            await session.execute(delete(AuthSession).where(AuthSession.employee_id.in_(existing_ids)))
            await session.execute(delete(Employee).where(Employee.id.in_(existing_ids)))
        admin = Employee(
            employee_number=f"{PREFIX}ADMIN", full_name="통합관리자",
            date_of_birth=date(1983, 3, 4), email="core-flow-admin@example.com",
            password_hash=PASSWORD_HASH.hash(ADMIN_PASSWORD), role=EmployeeRole.ADMIN,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    app.dependency_overrides[get_background_check_client] = lambda: CoreFlowBackgroundClient()
    transport = httpx.ASGITransport(app=app)
    try:
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as admin_client,
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as employee_client,
        ):
            assert (await login(admin_client, admin.email, ADMIN_PASSWORD)).status_code == 200
            admin_csrf = admin_client.cookies["employee_portal_csrf"]

            created = await admin_client.post(
                "/admin/employees",
                json={
                    "employee_number": f"{PREFIX}EMPLOYEE", "full_name": "남궁통합",
                    "date_of_birth": "1994-04-05", "email": "core-flow-employee@example.com",
                    "phone": "010-1000-2000", "address": "서울특별시",
                    "initial_password": EMPLOYEE_PASSWORD,
                },
                headers={"X-CSRF-Token": admin_csrf},
            )
            assert created.status_code == 201
            employee_id = created.json()["id"]

            assert (await login(employee_client, "core-flow-employee@example.com", EMPLOYEE_PASSWORD)).status_code == 200
            employee_csrf = employee_client.cookies["employee_portal_csrf"]
            updated = await employee_client.patch(
                "/employees/me", json={"phone": "010-9999-8888", "address": "부산광역시"},
                headers={"X-CSRF-Token": employee_csrf},
            )
            assert updated.status_code == 200 and updated.json()["address"] == "부산광역시"

            assert (await employee_client.get("/admin/employees")).status_code == 403
            assert (await employee_client.get(f"/admin/employees/{employee_id}/background-checks/proposal")).status_code == 403

            proposal = await admin_client.get(f"/admin/employees/{employee_id}/background-checks/proposal")
            assert proposal.status_code == 200 and proposal.json()["lastName"] == "남궁"
            requested = await admin_client.post(
                f"/admin/employees/{employee_id}/background-checks",
                json={"firstName": "확정이름", "lastName": "확정성", "dateOfBirth": "1994-04-05"},
                headers={"X-CSRF-Token": admin_csrf},
            )
            assert requested.status_code == 201 and requested.json()["status"] == "pending"

            history = await admin_client.get(f"/admin/employees/{employee_id}/background-checks")
            detail = await admin_client.get(f"/admin/employees/{employee_id}/background-checks/CHK-CORE-FLOW")
            assert history.status_code == 200 and history.json()["checks"][0]["requestedByName"] == "통합관리자"
            assert detail.status_code == 200 and detail.json()["status"] == "clear"
            assert detail.json()["criminalRecord"] is False

            terminated = await admin_client.post(
                f"/admin/employees/{employee_id}/terminate",
                headers={"X-CSRF-Token": admin_csrf},
            )
            assert terminated.status_code == 200 and terminated.json()["status"] == "TERMINATED"
            assert (await employee_client.get("/employees/me")).status_code == 401

            employee_client.cookies.clear()
            assert (await login(employee_client, "core-flow-employee@example.com", EMPLOYEE_PASSWORD)).status_code == 401
    finally:
        app.dependency_overrides.pop(get_background_check_client, None)
        async with SessionFactory() as session:
            ids = list(await session.scalars(select(Employee.id).where(Employee.employee_number.like(f"{PREFIX}%"))))
            if ids:
                await session.execute(delete(BackgroundCheckRequest).where(BackgroundCheckRequest.employee_id.in_(ids)))
                await session.execute(delete(AuthSession).where(AuthSession.employee_id.in_(ids)))
                await session.execute(delete(Employee).where(Employee.id.in_(ids)))
                await session.commit()
