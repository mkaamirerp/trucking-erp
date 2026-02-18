from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy import Column, Integer, Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.person import Person, PersonRole
from app.models.driver_onboarding_submission import DriverOnboardingSubmission
from app.models.tenant import Tenant
from app.deps.auth import CurrentUser
from app.routers.driver_onboarding import create_submission, submit_submission, approve_submission
from app.schemas.driver_onboarding import DriverOnboardingSubmissionCreate


def test_driver_onboarding_create_submit_approve() -> None:
    async def run() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        # Minimal table to satisfy FK on drivers.payee_id
        Table("payees", Base.metadata, Column("id", Integer, primary_key=True))

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with SessionLocal() as db:
            tenant = Tenant(id=1, name="Test Tenant", slug="test", status="active")
            db.add(tenant)
            await db.commit()

            current_user = CurrentUser(
                user=SimpleNamespace(id="user-1", email="u@example.com", first_name="U", last_name="One"),
                tenant=SimpleNamespace(id=1, slug="test", name="Test Tenant"),
                role="ADMIN",
                member_id=1,
            )

            payload = DriverOnboardingSubmissionCreate(
                first_name="Ada",
                last_name="Lovelace",
                email="ada@example.com",
                phone="+14165551212",
                submit=False,
            )
            created = await create_submission(payload, tenant_id=1, current_user=current_user, db=db)
            submission = created["submission"]
            assert submission.status == "DRAFT"

            submitted = await submit_submission(submission.id, tenant_id=1, current_user=current_user, db=db)
            assert submitted.status == "SUBMITTED"

            approved = await approve_submission(submission.id, tenant_id=1, current_user=current_user, db=db)
            assert approved["submission"].status == "APPROVED"
            assert approved["person"] is not None
            assert approved["person"].first_name == "Ada"
            assert approved["person"].last_name == "Lovelace"

            person = await db.scalar(select(Person).where(Person.tenant_id == 1))
            assert person is not None
            assert person.first_name == "Ada"
            # Status lives on submission; DRIVER role is active after approve
            role = await db.scalar(select(PersonRole).where(PersonRole.person_id == person.id, PersonRole.role_code == "DRIVER"))
            assert role is not None and role.is_active is True

    asyncio.run(run())
