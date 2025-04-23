from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    token = Column(String, primary_key=True)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @classmethod
    async def is_blacklisted(cls, db, token: str) -> bool:
        result = await db.get(cls, token)
        return result is not None

    @classmethod
    async def add_token(cls, db, token: str, expires_at):
        blacklisted_token = cls(token=token, expires_at=expires_at)
        db.add(blacklisted_token)
        await db.commit() 