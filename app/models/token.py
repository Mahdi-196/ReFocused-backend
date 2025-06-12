from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.db.database import Base

class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    token = Column(String, primary_key=True)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @classmethod
    def is_blacklisted(cls, db, token: str) -> bool:
        """Check if a token is blacklisted using synchronous database session."""
        result = db.query(cls).filter(cls.token == token).first()
        return result is not None

    @classmethod
    def add_token(cls, db, token: str, expires_at):
        """Add a token to the blacklist using synchronous database session."""
        blacklisted_token = cls(token=token, expires_at=expires_at)
        db.add(blacklisted_token)
        db.commit() 