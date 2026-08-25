from collections.abc import Iterable
from typing import Any

from app.core.config import Settings
from app.models import Employee, EmployeeRole
from app.seed import PASSWORD_HASH, SEED_EMPLOYEES, seed_employees, seed_is_allowed


class ScalarResult:
    def __init__(self, employees: Iterable[Employee]) -> None:
        self._employees = list(employees)

    def all(self) -> list[Employee]:
        return self._employees


class ExecuteResult:
    def __init__(self, employees: Iterable[Employee]) -> None:
        self._employees = employees

    def scalars(self) -> ScalarResult:
        return ScalarResult(self._employees)


class FakeSession:
    def __init__(self, employees: Iterable[Employee] = ()) -> None:
        self.employees = list(employees)
        self.added: list[Employee] = []

    async def execute(self, _: Any) -> ExecuteResult:
        return ExecuteResult(self.employees)

    def add_all(self, employees: Iterable[Employee]) -> None:
        self.added.extend(employees)


def test_seed_permission_defaults_and_explicit_production_opt_in() -> None:
    common = {"_env_file": None, "postgres_password": "test-password"}

    assert seed_is_allowed(Settings(app_env="development", **common))
    assert not seed_is_allowed(Settings(app_env="production", **common))
    assert seed_is_allowed(Settings(app_env="production", allow_seed=True, **common))
    assert not seed_is_allowed(Settings(app_env="test", **common))


async def test_seed_creates_admin_employees_and_argon2id_hashes() -> None:
    session = FakeSession()

    created = await seed_employees(session, "admin-secret", "employee-secret")  # type: ignore[arg-type]

    assert created == 4
    assert len(session.added) == 4
    assert sum(item.role is EmployeeRole.ADMIN for item in session.added) == 1
    assert any(item.full_name == "남궁서준" for item in session.added)
    assert all(item.password_hash.startswith("$argon2id$") for item in session.added)
    admin = next(item for item in session.added if item.role is EmployeeRole.ADMIN)
    employee = next(item for item in session.added if item.role is EmployeeRole.EMPLOYEE)
    assert PASSWORD_HASH.verify("admin-secret", admin.password_hash)
    assert PASSWORD_HASH.verify("employee-secret", employee.password_hash)


async def test_seed_is_idempotent() -> None:
    existing = [
        Employee(
            employee_number=item.employee_number,
            full_name=item.full_name,
            date_of_birth=item.date_of_birth,
            email=item.email,
            password_hash="$argon2id$existing",
            role=item.role,
        )
        for item in SEED_EMPLOYEES
    ]
    session = FakeSession(existing)

    created = await seed_employees(
        session,
        "admin-secret",
        "employee-secret",
        lambda _: "unused",  # type: ignore[arg-type]
        lambda _password, _hash: True,
    )

    assert created == 0
    assert session.added == []


async def test_seed_updates_a_changed_seed_password_without_duplicates() -> None:
    item = SEED_EMPLOYEES[0]
    existing = Employee(
        employee_number=item.employee_number,
        full_name=item.full_name,
        date_of_birth=item.date_of_birth,
        email=item.email,
        password_hash="old-hash",
        role=item.role,
    )
    session = FakeSession([existing])

    created = await seed_employees(
        session,  # type: ignore[arg-type]
        "new-admin-secret",
        "employee-secret",
        lambda password: f"hashed:{password}",
        lambda _password, _hash: False,
    )

    assert created == 3
    assert existing.password_hash == "hashed:new-admin-secret"
