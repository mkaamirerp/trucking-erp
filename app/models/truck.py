from sqlalchemy import Column, Integer, String
from app.core.database import Base

class Truck(Base):
    __tablename__ = "trucks"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String, unique=True, index=True, nullable=False)
    model = Column(String, nullable=False)
    driver_name = Column(String, nullable=True)
