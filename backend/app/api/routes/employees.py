from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AuthContext, get_current_employee, require_csrf
from app.core.database import get_db_session
from app.models import Employee
from app.schemas.employee import EmployeeSelfResponse, EmployeeSelfUpdate


router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/me", response_model=EmployeeSelfResponse)
async def get_my_profile(
    employee: Employee = Depends(get_current_employee),
) -> Employee:
    return employee


@router.patch("/me", response_model=EmployeeSelfResponse)
async def update_my_profile(
    payload: EmployeeSelfUpdate,
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db_session),
) -> Employee:
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(auth.employee, field, value)

    await db.commit()
    await db.refresh(auth.employee)
    return auth.employee
