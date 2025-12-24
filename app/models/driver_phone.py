from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DriverPhone(Base):
    __tablename__ = "driver_phones"

    __table_args__ = (
        # Prevent duplicate entries for the same driver
        UniqueConstraint(
            "driver_id",
            "country_code",
            "phone_number",
            name="uq_driver_phone_dedupe",
        ),

        # Enforce only one primary phone per driver (PostgreSQL partial unique index)
        Index(
            "ux_driver_primary_phone",
            "driver_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),

        # Helpful indexes
        Index("ix_driver_phones_driver_id", "driver_id"),
        Index("ix_driver_phones_phone_number", "phone_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    country_code: Mapped[str] = mapped_column(String(5), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)

    phone_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="mobile",
    )

    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    driver = relationship("Driver", back_populates="phones")
