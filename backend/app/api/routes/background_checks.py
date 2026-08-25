import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.dependencies import AuthContext, require_admin, require_csrf
from app.core.database import get_db_session
from app.models import BackgroundCheckRequest, BackgroundCheckStatus, Employee
from app.schemas.background_check import (
    BackgroundCheckCreatedResponse,
    BackgroundCheckCreateRequest,
    BackgroundCheckDetailResponse,
    BackgroundCheckHistoryItem,
    BackgroundCheckHistoryResponse,
    NameProposalResponse,
)
from app.services.background_checks import BackgroundCheckClient, BackgroundCheckProviderError, get_background_check_client


COMPOUND_SURNAMES = ("남궁", "황보", "제갈", "사공", "선우", "서문", "독고", "동방", "어금", "망절", "무본", "황목", "등정", "장곡", "강전")
router = APIRouter(prefix="/admin/employees/{employee_id}/background-checks", tags=["background checks"])


def propose_korean_name(full_name: str) -> tuple[str, str]:
    normalized = "".join(full_name.split())
    surname_length = 2 if normalized.startswith(COMPOUND_SURNAMES) else 1
    return normalized[surname_length:], normalized[:surname_length]


async def employee_or_404(db: AsyncSession, employee_id: uuid.UUID) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


def raise_provider_read_error(exc: BackgroundCheckProviderError) -> None:
    if exc.kind == "not_found":
        raise HTTPException(status_code=404, detail="Background check not found") from exc
    if exc.kind == "unavailable":
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        raise HTTPException(status_code=503, detail="Background check provider is unavailable", headers=headers) from exc
    if exc.kind == "timeout":
        raise HTTPException(status_code=504, detail="Background check provider timed out") from exc
    raise HTTPException(status_code=502, detail="Invalid response from background check provider") from exc


@router.get("/proposal", response_model=NameProposalResponse)
async def get_background_check_proposal(employee_id: uuid.UUID, _: Employee = Depends(require_admin), db: AsyncSession = Depends(get_db_session)) -> NameProposalResponse:
    employee = await employee_or_404(db, employee_id)
    first_name, last_name = propose_korean_name(employee.full_name)
    return NameProposalResponse(firstName=first_name, lastName=last_name, dateOfBirth=employee.date_of_birth)


@router.post("", response_model=BackgroundCheckCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_background_check(
    employee_id: uuid.UUID,
    payload: BackgroundCheckCreateRequest,
    admin: Employee = Depends(require_admin),
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db_session),
    client: BackgroundCheckClient = Depends(get_background_check_client),
) -> BackgroundCheckCreatedResponse:
    del auth
    employee = await employee_or_404(db, employee_id)
    try:
        external = await client.create(employee_id=employee.employee_number, first_name=payload.firstName, last_name=payload.lastName, date_of_birth=payload.dateOfBirth.isoformat())
    except BackgroundCheckProviderError as exc:
        if exc.kind == "bad_request":
            raise HTTPException(status_code=422, detail="Background check provider rejected the request") from exc
        if exc.kind == "timeout":
            raise HTTPException(status_code=504, detail="Background check request timed out; outcome is unknown and was not retried") from exc
        if exc.kind == "unavailable":
            headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
            raise HTTPException(status_code=503, detail="Background check provider is unavailable", headers=headers) from exc
        raise HTTPException(status_code=502, detail="Invalid response from background check provider") from exc

    if external.employeeId != employee.employee_number:
        raise HTTPException(status_code=502, detail="Invalid response from background check provider")

    tracking = BackgroundCheckRequest(
        employee_id=employee.id,
        external_check_id=external.checkId,
        employee_number_snapshot=employee.employee_number,
        first_name_snapshot=payload.firstName,
        last_name_snapshot=payload.lastName,
        date_of_birth_snapshot=payload.dateOfBirth,
        requested_by=admin.id,
        initial_status=BackgroundCheckStatus(external.status),
        last_status=BackgroundCheckStatus(external.status),
    )
    db.add(tracking)
    await db.commit()
    await db.refresh(tracking)
    return BackgroundCheckCreatedResponse(
        id=tracking.id, checkId=tracking.external_check_id,
        employeeId=tracking.employee_number_snapshot,
        firstName=tracking.first_name_snapshot, lastName=tracking.last_name_snapshot,
        dateOfBirth=tracking.date_of_birth_snapshot, requestedBy=tracking.requested_by,
        requestedAt=tracking.requested_at, status=tracking.initial_status.value,
    )


@router.get("", response_model=BackgroundCheckHistoryResponse)
async def list_background_checks(
    employee_id: uuid.UUID,
    _: Employee = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    client: BackgroundCheckClient = Depends(get_background_check_client),
) -> BackgroundCheckHistoryResponse:
    employee = await employee_or_404(db, employee_id)
    try:
        external = await client.list_for_employee(employee.employee_number)
    except BackgroundCheckProviderError as exc:
        raise_provider_read_error(exc)
        raise AssertionError("unreachable")
    if external.employeeId != employee.employee_number:
        raise HTTPException(status_code=502, detail="Invalid response from background check provider")

    result = await db.execute(
        select(BackgroundCheckRequest)
        .options(joinedload(BackgroundCheckRequest.requester))
        .where(BackgroundCheckRequest.employee_id == employee.id)
    )
    local_by_check = {item.external_check_id: item for item in result.scalars().all()}
    checked_at = datetime.now(timezone.utc)
    items: list[BackgroundCheckHistoryItem] = []
    for check in sorted(external.checks, key=lambda item: item.createdAt or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        local = local_by_check.get(check.checkId)
        if local:
            local.last_status = BackgroundCheckStatus(check.status)
            local.last_checked_at = checked_at
        items.append(BackgroundCheckHistoryItem(
            checkId=check.checkId, status=check.status,
            createdAt=check.createdAt, completedAt=check.completedAt,
            localRequestId=local.id if local else None,
            requestedBy=local.requested_by if local else None,
            requestedByName=local.requester.full_name if local else None,
            requestedFirstName=local.first_name_snapshot if local else None,
            requestedLastName=local.last_name_snapshot if local else None,
        ))
    await db.commit()
    return BackgroundCheckHistoryResponse(employeeId=employee.employee_number, checks=items)


@router.get("/{check_id}", response_model=BackgroundCheckDetailResponse)
async def get_background_check(
    employee_id: uuid.UUID,
    check_id: str,
    _: Employee = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    client: BackgroundCheckClient = Depends(get_background_check_client),
) -> BackgroundCheckDetailResponse:
    employee = await employee_or_404(db, employee_id)
    try:
        external = await client.get(check_id)
    except BackgroundCheckProviderError as exc:
        raise_provider_read_error(exc)
        raise AssertionError("unreachable")
    if external.employeeId != employee.employee_number or external.checkId != check_id:
        raise HTTPException(status_code=404, detail="Background check not found for employee")

    local = await db.scalar(
        select(BackgroundCheckRequest).where(
            BackgroundCheckRequest.employee_id == employee.id,
            BackgroundCheckRequest.external_check_id == check_id,
        )
    )
    if local:
        local.last_status = BackgroundCheckStatus(external.status)
        local.last_checked_at = datetime.now(timezone.utc)
        await db.commit()
    return BackgroundCheckDetailResponse(**external.model_dump())
