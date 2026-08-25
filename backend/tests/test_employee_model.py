from datetime import date

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models import Employee, EmployeeRole, EmployeeStatus


def test_employee_defaults_and_email_normalization() -> None:
    employee = Employee(
        employee_number="E9999",
        full_name="테스트직원",
        date_of_birth=date(1999, 1, 1),
        email="  TEST@Example.COM ",
        password_hash="$argon2id$test",
    )

    assert employee.email == "test@example.com"
    assert Employee.role.default.arg is EmployeeRole.EMPLOYEE
    assert Employee.status.default.arg is EmployeeStatus.ACTIVE


def test_employee_table_constraints() -> None:
    constraints = Employee.__table__.constraints
    constraint_names = {constraint.name for constraint in constraints}
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("employee_number",) in unique_columns
    assert ("email",) in unique_columns
    assert "ck_employees_email_lowercase" in constraint_names
    assert "ck_employees_termination_state" in constraint_names
    assert any(isinstance(item, CheckConstraint) for item in constraints)


def test_employee_has_self_referencing_terminator() -> None:
    foreign_key = next(iter(Employee.__table__.c.terminated_by.foreign_keys))

    assert foreign_key.target_fullname == "employees.id"
    assert foreign_key.ondelete == "SET NULL"
