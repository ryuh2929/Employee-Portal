import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuthContext, require_admin, require_csrf
from app.core.database import get_db_session
from app.core.security import PASSWORD_HASH
from app.models import AuthSession, Employee, EmployeeRole, EmployeeStatus
from app.schemas.admin_employee import (
    AdminEmployeeCreate,
    AdminEmployeeDetail,
    AdminEmployeeListItem,
    AdminEmployeeUpdate,
)


router = APIRouter(prefix="/admin/employees", tags=["admin employees"])


async def employee_or_404(db: AsyncSession, employee_id: uuid.UUID) -> Employee:
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


async def commit_or_duplicate(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee number or email already exists",
        ) from exc


@router.get("", response_model=list[AdminEmployeeListItem])
async def list_employees(
    search: str | None = Query(default=None, max_length=100),
    _: Employee = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> list[Employee]:
    statement = select(Employee).order_by(Employee.full_name, Employee.employee_number)
    if search and (term := search.strip()):
        statement = statement.where(
            or_(Employee.full_name.ilike(f"%{term}%"), Employee.employee_number.ilike(f"%{term}%"))
        )
    result = await db.execute(statement)
    return list(result.scalars().all())


@router.get("/{employee_id}", response_model=AdminEmployeeDetail)
async def get_employee(
    employee_id: uuid.UUID,
    _: Employee = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Employee:
    return await employee_or_404(db, employee_id)


@router.post("", response_model=AdminEmployeeDetail, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: AdminEmployeeCreate,
    _: Employee = Depends(require_admin),
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db_session),
) -> Employee:
    del auth
    values = payload.model_dump(exclude={"initial_password"})
    employee = Employee(
        **values,
        password_hash=PASSWORD_HASH.hash(payload.initial_password),
        role=EmployeeRole.EMPLOYEE,
        status=EmployeeStatus.ACTIVE,
    )
    db.add(employee)
    await commit_or_duplicate(db)
    await db.refresh(employee)
    return employee


@router.patch("/{employee_id}", response_model=AdminEmployeeDetail)
async def update_employee(
    employee_id: uuid.UUID,
    payload: AdminEmployeeUpdate,
    _: Employee = Depends(require_admin),
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db_session),
) -> Employee:
    del auth
    employee = await employee_or_404(db, employee_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(employee, field, value)
    await commit_or_duplicate(db)
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/terminate", response_model=AdminEmployeeDetail)
async def terminate_employee(
    employee_id: uuid.UUID,
    admin: Employee = Depends(require_admin),
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db_session),
) -> Employee:
    del auth
    result = await db.execute(
        select(Employee).where(Employee.id == employee_id).with_for_update()
    )
    employee = result.scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    now = datetime.now(timezone.utc)
    if employee.status is EmployeeStatus.ACTIVE:
        employee.status = EmployeeStatus.TERMINATED
        employee.terminated_at = now
        employee.terminated_by = admin.id

    await db.execute(
        update(AuthSession)
        .where(
            AuthSession.employee_id == employee.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.commit()
    await db.refresh(employee)
    return employee
