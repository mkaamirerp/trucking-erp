from sqlalchemy import BigInteger, Date, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "person_id"],
            ["people.tenant_id", "people.id"],
            name="fk_drivers_tenant_person_to_people",
            ondelete="SET NULL",
        ),
        Index("ix_drivers_person_id", "person_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("payees.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hire_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    termination_date: Mapped[Date | None] = mapped_column(Date, nullable=True)

    # License / compliance (global, free-text friendly)
    issuing_country: Mapped[str | None] = mapped_column(String(10), nullable=True)
    issuing_region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    license_issue_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    license_expiry_date: Mapped[Date | None] = mapped_column(Date, nullable=True, index=True)
    person_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    phones = relationship(
        "DriverPhone",
        back_populates="driver",
        cascade="all, delete-orphan",
    )

    loads = relationship("Load", back_populates="driver")
