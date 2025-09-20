from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.db.models import Base

class SecurityLog(Base):
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    event_type = Column(String, index=True)
    details = Column(Text)
    user_id = Column(Integer, index=True, nullable=True)
    ip_address = Column(String)
    user_agent = Column(String, nullable=True) 