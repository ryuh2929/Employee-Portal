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
from app.models import AuthSession, BackgroundCheckRequest, BackgroundCheckStatus, Employee, EmployeeRole
from app.services.background_checks import (
    BackgroundCheckClient,
    BackgroundCheckProviderError,
    ExternalBackgroundCheckCreated,
    ExternalBackgroundCheckList,
    ExternalBackgroundCheckResult,
    ExternalBackgroundCheckSummary,
    get_background_check_client,
)
from app.api.routes.background_checks import COMPOUND_SURNAMES, propose_korean_name


PREFIX = "BGCHECK-"


class FakeBackgroundClient:
    def __init__(self, statuses: list[str] | None = None, error: BackgroundCheckProviderError | None = None) -> None:
        self.statuses = statuses or ["pending"]
        self.error = error
        self.calls: list[dict[str, str]] = []

    async def create(self, **kwargs: str) -> ExternalBackgroundCheckCreated:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        status = self.statuses[len(self.calls) - 1]
        return ExternalBackgroundCheckCreated(
            checkId=f"CHK-TEST-{len(self.calls)}", employeeId=kwargs["employee_id"],
            status=status, createdAt="2026-08-25T09:00:00Z",
        )


class FakeReadClient:
    def __init__(self, employee_number: str) -> None:
        self.employee_number = employee_number
        self.list_error: BackgroundCheckProviderError | None = None
        self.get_error: BackgroundCheckProviderError | None = None
        self.detail_sequences: dict[str, list[str]] = {}
        self.get_counts: dict[str, int] = {}

    async def list_for_employee(self, employee_id: str) -> ExternalBackgroundCheckList:
        if self.list_error:
            raise self.list_error
        return ExternalBackgroundCheckList(
            employeeId=employee_id,
            checks=[
                ExternalBackgroundCheckSummary(checkId="CHK-TEST-1", status="pending", createdAt="2026-08-25T09:00:00Z"),
                ExternalBackgroundCheckSummary(checkId="CHK-EXTERNAL", status="clear", createdAt="2026-08-24T09:00:00Z", completedAt="2026-08-24T09:01:00Z"),
            ], totalCount=2,
        )

    async def get(self, check_id: str) -> ExternalBackgroundCheckResult:
        if self.get_error:
            raise self.get_error
        count = self.get_counts.get(check_id, 0)
        self.get_counts[check_id] = count + 1
        sequence = self.detail_sequences.get(check_id, ["clear"])
        status = sequence[min(count, len(sequence) - 1)]
        completed = None if status == "pending" else "2026-08-25T09:03:00Z"
        return ExternalBackgroundCheckResult(
            checkId=check_id, employeeId=self.employee_number,
            firstName="수정이름", lastName="수정성", dateOfBirth="1991-02-03",
            status=status, criminalRecord=None if status == "pending" else False,
            educationVerified=None if status == "pending" else True,
            employmentVerified=None if status == "pending" else True,
            creditScore=None if status == "pending" else "good",
            createdAt="2026-08-25T09:00:00Z", completedAt=completed,
        )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def background_context() -> AsyncIterator[dict[str, object]]:
    await engine.dispose(close=False)
    async with SessionFactory() as session:
        await session.execute(delete(Employee).where(Employee.employee_number.like(f"{PREFIX}%")))
        admin = Employee(
            employee_number=f"{PREFIX}ADMIN", full_name="검사관리자", date_of_birth=date(1982, 1, 1),
            email="bgcheck-admin@example.com", password_hash=PASSWORD_HASH.hash("password"), role=EmployeeRole.ADMIN,
        )
        employee = Employee(
            employee_number=f"{PREFIX}EMPLOYEE", full_name="남궁서준", date_of_birth=date(1990, 1, 30),
            email="bgcheck-employee@example.com", password_hash=PASSWORD_HASH.hash("password"),
        )
        session.add_all([admin, employee])
        await session.commit()
        await session.refresh(admin); await session.refresh(employee)
        tokens: dict[str, tuple[str, str]] = {}
        for name, account in (("admin", admin), ("employee", employee)):
            session_token, csrf_token = generate_token(), generate_token()
            tokens[name] = (session_token, csrf_token)
            session.add(AuthSession(
                employee_id=account.id, token_hash=hash_token(session_token),
                csrf_token_hash=hash_token(csrf_token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ))
        await session.commit()
    yield {"admin": admin, "employee": employee, "tokens": tokens}
    app.dependency_overrides.pop(get_background_check_client, None)
    async with SessionFactory() as session:
        ids = list(await session.scalars(select(Employee.id).where(Employee.employee_number.like(f"{PREFIX}%"))))
        if ids:
            await session.execute(delete(BackgroundCheckRequest).where(BackgroundCheckRequest.employee_id.in_(ids)))
            await session.execute(delete(AuthSession).where(AuthSession.employee_id.in_(ids)))
            await session.execute(delete(Employee).where(Employee.id.in_(ids)))
            await session.commit()


def client_for(context: dict[str, object], account: str) -> httpx.AsyncClient:
    settings = get_settings(); tokens = context["tokens"]; assert isinstance(tokens, dict)
    session_token, csrf_token = tokens[account]
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    client.cookies.set(settings.session_cookie_name, session_token)
    client.cookies.set(settings.csrf_cookie_name, csrf_token)
    return client


def csrf(context: dict[str, object], account: str = "admin") -> dict[str, str]:
    tokens = context["tokens"]; assert isinstance(tokens, dict)
    return {"X-CSRF-Token": tokens[account][1]}


def test_korean_name_proposal_supports_normal_and_every_compound_surname() -> None:
    assert propose_korean_name("김민수") == ("민수", "김")
    assert propose_korean_name(" 김 민수 ") == ("민수", "김")
    for surname in COMPOUND_SURNAMES:
        assert propose_korean_name(f"{surname}서준") == ("서준", surname)


@pytest.mark.asyncio(loop_scope="module")
async def test_admin_gets_name_and_birth_date_proposal(background_context: dict[str, object]) -> None:
    employee = background_context["employee"]; assert isinstance(employee, Employee)
    async with client_for(background_context, "admin") as client:
        response = await client.get(f"/admin/employees/{employee.id}/background-checks/proposal")
    assert response.status_code == 200
    assert response.json() == {"firstName": "서준", "lastName": "남궁", "dateOfBirth": "1990-01-30"}


@pytest.mark.asyncio(loop_scope="module")
async def test_confirmed_values_are_sent_and_snapshotted_for_every_initial_status(background_context: dict[str, object]) -> None:
    admin, employee = background_context["admin"], background_context["employee"]
    assert isinstance(admin, Employee) and isinstance(employee, Employee)
    fake = FakeBackgroundClient(["pending", "clear", "flagged"])
    app.dependency_overrides[get_background_check_client] = lambda: fake
    payload = {"firstName": "관리자수정이름", "lastName": "수정성", "dateOfBirth": "1991-02-03"}
    async with client_for(background_context, "admin") as client:
        responses = [await client.post(f"/admin/employees/{employee.id}/background-checks", json=payload, headers=csrf(background_context)) for _ in range(3)]
    assert [item.status_code for item in responses] == [201, 201, 201]
    assert [item.json()["status"] for item in responses] == ["pending", "clear", "flagged"]
    assert fake.calls[0] == {"employee_id": employee.employee_number, "first_name": "관리자수정이름", "last_name": "수정성", "date_of_birth": "1991-02-03"}

    async with SessionFactory() as session:
        records = list(await session.scalars(select(BackgroundCheckRequest).where(BackgroundCheckRequest.employee_id == employee.id).order_by(BackgroundCheckRequest.external_check_id)))
    assert len(records) == 3
    assert all(item.employee_number_snapshot == employee.employee_number for item in records)
    assert all(item.first_name_snapshot == "관리자수정이름" and item.last_name_snapshot == "수정성" for item in records)
    assert all(item.date_of_birth_snapshot == date(1991, 2, 3) and item.requested_by == admin.id for item in records)


@pytest.mark.asyncio(loop_scope="module")
async def test_regular_employee_is_forbidden_from_proposal_and_creation(background_context: dict[str, object]) -> None:
    employee = background_context["employee"]; assert isinstance(employee, Employee)
    fake = FakeBackgroundClient(); app.dependency_overrides[get_background_check_client] = lambda: fake
    async with client_for(background_context, "employee") as client:
        proposal = await client.get(f"/admin/employees/{employee.id}/background-checks/proposal")
        creation = await client.post(f"/admin/employees/{employee.id}/background-checks", json={"firstName": "서준", "lastName": "남궁", "dateOfBirth": "1990-01-30"}, headers=csrf(background_context, "employee"))
    assert proposal.status_code == 403 and creation.status_code == 403
    assert fake.calls == []


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(("provider_error", "expected", "retry_after"), [
    (BackgroundCheckProviderError("bad_request"), 422, None),
    (BackgroundCheckProviderError("server_error"), 502, None),
    (BackgroundCheckProviderError("unavailable", 30), 503, "30"),
    (BackgroundCheckProviderError("timeout"), 504, None),
])
async def test_external_errors_are_safely_mapped_without_retry(
    background_context: dict[str, object], provider_error: BackgroundCheckProviderError, expected: int, retry_after: str | None
) -> None:
    employee = background_context["employee"]; assert isinstance(employee, Employee)
    fake = FakeBackgroundClient(error=provider_error); app.dependency_overrides[get_background_check_client] = lambda: fake
    async with client_for(background_context, "admin") as client:
        response = await client.post(f"/admin/employees/{employee.id}/background-checks", json={"firstName": "서준", "lastName": "남궁", "dateOfBirth": "1990-01-30"}, headers=csrf(background_context))
    assert response.status_code == expected
    assert len(fake.calls) == 1
    if retry_after is not None:
        assert response.headers["Retry-After"] == retry_after


@pytest.mark.asyncio(loop_scope="module")
async def test_http_client_recognizes_provider_errors_and_never_retries_post() -> None:
    calls = 0
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls; calls += 1
        raise httpx.ReadTimeout("timeout", request=request)
    client = BackgroundCheckClient("https://provider.test", 1, httpx.MockTransport(timeout_handler))
    with pytest.raises(BackgroundCheckProviderError) as exc_info:
        await client.create(employee_id="E1", first_name="민수", last_name="김", date_of_birth="1990-01-01")
    assert exc_info.value.kind == "timeout"
    assert calls == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_external_history_is_merged_with_local_request_information(
    background_context: dict[str, object],
) -> None:
    admin, employee = background_context["admin"], background_context["employee"]
    assert isinstance(admin, Employee) and isinstance(employee, Employee)
    fake = FakeReadClient(employee.employee_number)
    app.dependency_overrides[get_background_check_client] = lambda: fake
    async with client_for(background_context, "admin") as client:
        response = await client.get(f"/admin/employees/{employee.id}/background-checks")
    assert response.status_code == 200
    local, external_only = response.json()["checks"]
    assert local["checkId"] == "CHK-TEST-1"
    assert local["requestedBy"] == str(admin.id)
    assert local["requestedByName"] == admin.full_name
    assert local["requestedFirstName"] == "관리자수정이름"
    assert external_only["localRequestId"] is None


@pytest.mark.asyncio(loop_scope="module")
async def test_repeated_pending_then_clear_or_flagged_updates_only_local_status_metadata(
    background_context: dict[str, object],
) -> None:
    employee = background_context["employee"]; assert isinstance(employee, Employee)
    fake = FakeReadClient(employee.employee_number)
    fake.detail_sequences = {
        "CHK-TEST-1": ["pending", "pending", "clear"],
        "CHK-TEST-2": ["pending", "flagged"],
    }
    app.dependency_overrides[get_background_check_client] = lambda: fake
    async with client_for(background_context, "admin") as client:
        clear_flow = [await client.get(f"/admin/employees/{employee.id}/background-checks/CHK-TEST-1") for _ in range(3)]
        flagged_flow = [await client.get(f"/admin/employees/{employee.id}/background-checks/CHK-TEST-2") for _ in range(2)]
    assert [item.json()["status"] for item in clear_flow] == ["pending", "pending", "clear"]
    assert [item.json()["status"] for item in flagged_flow] == ["pending", "flagged"]
    assert clear_flow[-1].json()["criminalRecord"] is False

    async with SessionFactory() as session:
        records = list(await session.scalars(select(BackgroundCheckRequest).where(BackgroundCheckRequest.employee_id == employee.id)))
    by_id = {item.external_check_id: item for item in records}
    assert by_id["CHK-TEST-1"].last_status is BackgroundCheckStatus.CLEAR
    assert by_id["CHK-TEST-2"].last_status is BackgroundCheckStatus.FLAGGED
    assert by_id["CHK-TEST-1"].last_checked_at is not None
    columns = set(BackgroundCheckRequest.__table__.columns.keys())
    assert not {"criminal_record", "education_verified", "employment_verified", "credit_score"} & columns


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize(("error", "status_code", "retry"), [
    (BackgroundCheckProviderError("not_found"), 404, None),
    (BackgroundCheckProviderError("server_error"), 502, None),
    (BackgroundCheckProviderError("unavailable", 45), 503, "45"),
    (BackgroundCheckProviderError("timeout"), 504, None),
])
async def test_read_errors_are_safely_mapped(
    background_context: dict[str, object], error: BackgroundCheckProviderError,
    status_code: int, retry: str | None,
) -> None:
    employee = background_context["employee"]; assert isinstance(employee, Employee)
    fake = FakeReadClient(employee.employee_number); fake.get_error = error
    app.dependency_overrides[get_background_check_client] = lambda: fake
    async with client_for(background_context, "admin") as client:
        response = await client.get(f"/admin/employees/{employee.id}/background-checks/CHK-ERROR")
    assert response.status_code == status_code
    if retry:
        assert response.headers["Retry-After"] == retry


@pytest.mark.asyncio(loop_scope="module")
async def test_regular_employee_cannot_read_history_or_detail(background_context: dict[str, object]) -> None:
    employee = background_context["employee"]; assert isinstance(employee, Employee)
    fake = FakeReadClient(employee.employee_number)
    app.dependency_overrides[get_background_check_client] = lambda: fake
    async with client_for(background_context, "employee") as client:
        history = await client.get(f"/admin/employees/{employee.id}/background-checks")
        detail = await client.get(f"/admin/employees/{employee.id}/background-checks/CHK-TEST-1")
    assert history.status_code == 403 and detail.status_code == 403


@pytest.mark.asyncio(loop_scope="module")
async def test_http_client_handles_nullable_detail_and_503_retry_after() -> None:
    responses = [
        httpx.Response(200, json={"checkId": "CHK-1", "employeeId": "E1", "status": "pending", "criminalRecord": None}),
        httpx.Response(503, json={"retryAfter": 60}),
    ]
    calls = 0
    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        response = responses[calls]; calls += 1
        return response
    client = BackgroundCheckClient("https://provider.test", 1, httpx.MockTransport(handler))
    detail = await client.get("CHK-1")
    assert detail.criminalRecord is None and detail.completedAt is None
    with pytest.raises(BackgroundCheckProviderError) as exc_info:
        await client.get("CHK-1")
    assert exc_info.value.kind == "unavailable" and exc_info.value.retry_after == 60
