from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Truck(Base):
    __tablename__ = "trucks"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    plate_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    # temporary field (we will replace later with driver_id FK)
    driver_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
