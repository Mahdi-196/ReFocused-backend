from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import engine, Base
from app.models.user import User
from app.models.log import SecurityLog
from app.models.token import TokenBlacklist
from app.core.security import get_password_hash
import asyncio
import logging

logger = logging.getLogger(__name__)

async def init_db():
    async with engine.begin() as conn:
        # Create all tables (including User, SecurityLog, TokenBlacklist)
        await conn.run_sync(Base.metadata.create_all)

    # Create initial admin user
    async with AsyncSession(engine) as session:
        # Check if admin user exists
        admin = await session.get(User, 1)
        if not admin:
            admin = User(
                email="admin@example.com",
                username="admin",
                hashed_password=get_password_hash("admin123"),
                full_name="Admin User",
                is_superuser=True
            )
            session.add(admin)
            await session.commit()

if __name__ == "__main__":
    asyncio.run(init_db()) 