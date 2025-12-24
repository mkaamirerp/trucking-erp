from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class DriverPhone(Base):
    __tablename__ = "driver_phones"

    id: Mapped[int] = mapped_column(primary_key=True)

    driver_id: Mapped[int] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    label: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(10))

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    notes: Mapped[str | None] = mapped_column(String(255))

    driver = relationship("Driver", back_populates="phones")
