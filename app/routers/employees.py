from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import date
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.models.payee import Payee
from app.models.enums import WorkerType, PayeeType
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.schemas.employee_role import EmployeeRoleCreate, EmployeeRoleOut, ROLE_CHOICES
from app.deps.tenant import require_tenant

router = APIRouter(prefix="/api/v1/employees", tags=["Employees"])


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    employee_number = payload.employee_number or payload.employee_code
    if not employee_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="employee_number is required")

    existing = await db.scalar(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.employee_number == employee_number)
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee number already exists")

    payee_id = payload.payee_id
    if payee_id is not None:
        payee = await db.scalar(
            select(Payee).where(
                Payee.id == payee_id,
                Payee.tenant_id == tenant_id,
                Payee.worker_type == WorkerType.EMPLOYEE_DRIVER,
                Payee.payee_type == PayeeType.DRIVER,
            )
        )
        if not payee:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payee must be an EMPLOYEE_DRIVER driver")
    else:
        # Create a payee on the fly using the employee number as display name
        payee = Payee(
            tenant_id=tenant_id,
            payee_type=PayeeType.DRIVER,
            worker_type=WorkerType.EMPLOYEE_DRIVER,
            display_name=employee_number,
            is_active=True,
        )
        db.add(payee)
        await db.flush()
        payee_id = payee.id

    employee = Employee(
        tenant_id=tenant_id,
        payee_id=payee_id,
        employee_number=employee_number,
        hire_date=payload.hire_date or date.today(),
        termination_date=payload.termination_date,
        employment_type=payload.employment_type or "FULL_TIME",
        is_active=payload.is_active,
    )
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = False,
):
    stmt = select(Employee).where(Employee.tenant_id == tenant_id)
    if not include_inactive:
        stmt = stmt.where(Employee.is_active.is_(True))
    result = await db.execute(stmt.order_by(Employee.id.desc()))
    return list(result.scalars().all())


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    employee = await db.scalar(
        select(Employee).where(Employee.id == employee_id, Employee.tenant_id == tenant_id)
    )
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    employee = await db.scalar(
        select(Employee).where(Employee.id == employee_id, Employee.tenant_id == tenant_id)
    )
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    data = payload.model_dump(exclude_unset=True)
    if "employee_code" in data and "employee_number" not in data:
        data["employee_number"] = data["employee_code"]
    # Enforce unique employee_number per tenant on update
    if "employee_number" in data:
        exists = await db.scalar(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.employee_number == data["employee_number"],
                Employee.id != employee_id,
            )
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee number already exists")

    if "payee_id" in data:
        payee = await db.scalar(
            select(Payee).where(
                Payee.id == data["payee_id"],
                Payee.tenant_id == tenant_id,
                Payee.worker_type == WorkerType.EMPLOYEE_DRIVER,
                Payee.payee_type == PayeeType.DRIVER,
            )
        )
        if not payee:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payee must be an EMPLOYEE_DRIVER driver")

    for k, v in data.items():
        setattr(employee, k, v)

    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/roles", response_model=EmployeeRoleOut, status_code=status.HTTP_201_CREATED)
async def add_employee_role(
    employee_id: int,
    payload: EmployeeRoleCreate,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    employee = await db.scalar(
        select(Employee).where(Employee.id == employee_id, Employee.tenant_id == tenant_id)
    )
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    if payload.role not in ROLE_CHOICES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    # Prevent duplicate role for same employee/tenant
    existing_role = await db.scalar(
        select(EmployeeRole).where(
            EmployeeRole.tenant_id == tenant_id,
            EmployeeRole.employee_id == employee_id,
            EmployeeRole.role == payload.role,
        )
    )
    if existing_role:
        return existing_role

    role = EmployeeRole(
        tenant_id=tenant_id,
        employee_id=employee_id,
        role=payload.role,
        is_primary=payload.is_primary,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.get("/{employee_id}/roles", response_model=list[EmployeeRoleOut])
async def list_employee_roles(
    employee_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(EmployeeRole).where(EmployeeRole.employee_id == employee_id, EmployeeRole.tenant_id == tenant_id)
    )
    return list(res.scalars().all())


@router.delete("/{employee_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee_role(
    employee_id: int,
    role_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(EmployeeRole).where(
            EmployeeRole.id == role_id,
            EmployeeRole.employee_id == employee_id,
            EmployeeRole.tenant_id == tenant_id,
        )
    )
    role = res.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    await db.execute(
        delete(EmployeeRole).where(
            EmployeeRole.id == role_id,
            EmployeeRole.employee_id == employee_id,
            EmployeeRole.tenant_id == tenant_id,
        )
    )
    await db.commit()
