import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from pwdlib import PasswordHash
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionFactory, dispose_engine
from app.models import Employee, EmployeeRole


PASSWORD_HASH = PasswordHash.recommended()


@dataclass(frozen=True)
class SeedEmployee:
    employee_number: str
    full_name: str
    date_of_birth: date
    email: str
    phone: str
    address: str
    role: EmployeeRole = EmployeeRole.EMPLOYEE


SEED_EMPLOYEES = (
    SeedEmployee(
        employee_number="A0001",
        full_name="김관리",
        date_of_birth=date(1985, 3, 12),
        email="admin@employee-portal.local",
        phone="010-1000-0001",
        address="서울특별시 중구",
        role=EmployeeRole.ADMIN,
    ),
    SeedEmployee(
        employee_number="E0001",
        full_name="박민준",
        date_of_birth=date(1992, 7, 8),
        email="minjun.park@employee-portal.local",
        phone="010-2000-0001",
        address="서울특별시 마포구",
    ),
    SeedEmployee(
        employee_number="E0002",
        full_name="이서연",
        date_of_birth=date(1995, 11, 21),
        email="seoyeon.lee@employee-portal.local",
        phone="010-2000-0002",
        address="경기도 성남시",
    ),
    SeedEmployee(
        employee_number="E0003",
        full_name="남궁서준",
        date_of_birth=date(1990, 1, 30),
        email="seojun.namgung@employee-portal.local",
        phone="010-2000-0003",
        address="인천광역시 연수구",
    ),
)


async def seed_employees(
    session: AsyncSession,
    admin_password: str,
    employee_password: str,
    hash_password: Callable[[str], str] = PASSWORD_HASH.hash,
    verify_password: Callable[[str, str], bool] = PASSWORD_HASH.verify,
) -> int:
    numbers = [item.employee_number for item in SEED_EMPLOYEES]
    emails = [item.email for item in SEED_EMPLOYEES]
    result = await session.execute(
        select(Employee).where(
            or_(Employee.employee_number.in_(numbers), Employee.email.in_(emails))
        )
    )
    existing = result.scalars().all()
    by_number = {employee.employee_number: employee for employee in existing}
    by_email = {employee.email: employee for employee in existing}

    additions: list[Employee] = []
    for item in SEED_EMPLOYEES:
        number_match = by_number.get(item.employee_number)
        email_match = by_email.get(item.email)
        if number_match or email_match:
            if number_match is not email_match:
                raise RuntimeError(
                    f"Seed identity conflict for {item.employee_number}/{item.email}"
                )
            existing_employee = number_match or email_match
            assert existing_employee is not None
            password = (
                admin_password
                if item.role is EmployeeRole.ADMIN
                else employee_password
            )
            if not verify_password(password, existing_employee.password_hash):
                existing_employee.password_hash = hash_password(password)
            continue

        password = admin_password if item.role is EmployeeRole.ADMIN else employee_password
        additions.append(
            Employee(
                employee_number=item.employee_number,
                full_name=item.full_name,
                date_of_birth=item.date_of_birth,
                email=item.email,
                password_hash=hash_password(password),
                phone=item.phone,
                address=item.address,
                role=item.role,
            )
        )

    session.add_all(additions)
    return len(additions)


async def run_seed() -> int:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise RuntimeError("Seed data can only be loaded in the development environment")
    if settings.seed_admin_password is None or settings.seed_employee_password is None:
        raise RuntimeError(
            "SEED_ADMIN_PASSWORD and SEED_EMPLOYEE_PASSWORD must be configured"
        )

    async with SessionFactory() as session:
        async with session.begin():
            return await seed_employees(
                session,
                settings.seed_admin_password.get_secret_value(),
                settings.seed_employee_password.get_secret_value(),
            )


async def main() -> None:
    try:
        created = await run_seed()
        print(f"Seed complete: {created} employee(s) created")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
