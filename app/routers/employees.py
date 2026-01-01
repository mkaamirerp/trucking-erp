from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.employee import Employee
from app.models.employee_role import EmployeeRole
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.schemas.employee_role import EmployeeRoleCreate, EmployeeRoleOut, ROLE_CHOICES

router = APIRouter(prefix="/api/v1/employees", tags=["Employees"])


def get_tenant_id(request: Request) -> int:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context missing")
    return int(tenant_id)


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
async def create_employee(payload: EmployeeCreate, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    # Enforce unique employee_code per tenant
    existing = await db.scalar(
        select(Employee).where(Employee.tenant_id == tenant_id, Employee.employee_code == payload.employee_code)
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee code already exists")

    employee = Employee(tenant_id=tenant_id, **payload.model_dump())
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    request: Request,
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = False,
):
    tenant_id = get_tenant_id(request)
    stmt = select(Employee).where(Employee.tenant_id == tenant_id)
    if not include_inactive:
        stmt = stmt.where(Employee.is_active.is_(True))
    result = await db.execute(stmt.order_by(Employee.id.desc()))
    return list(result.scalars().all())


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
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
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = get_tenant_id(request)
    employee = await db.scalar(
        select(Employee).where(Employee.id == employee_id, Employee.tenant_id == tenant_id)
    )
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    data = payload.model_dump(exclude_unset=True)
    # Enforce unique employee_code per tenant on update
    if "employee_code" in data:
        exists = await db.scalar(
            select(Employee).where(
                Employee.tenant_id == tenant_id,
                Employee.employee_code == data["employee_code"],
                Employee.id != employee_id,
            )
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee code already exists")

    for k, v in data.items():
        setattr(employee, k, v)

    await db.commit()
    await db.refresh(employee)
    return employee


@router.post("/{employee_id}/roles", response_model=EmployeeRoleOut, status_code=status.HTTP_201_CREATED)
async def add_employee_role(
    employee_id: int,
    payload: EmployeeRoleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = get_tenant_id(request)
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role already assigned to employee")

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
async def list_employee_roles(employee_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    res = await db.execute(
        select(EmployeeRole).where(EmployeeRole.employee_id == employee_id, EmployeeRole.tenant_id == tenant_id)
    )
    return list(res.scalars().all())


@router.delete("/{employee_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee_role(
    employee_id: int,
    role_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = get_tenant_id(request)
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
