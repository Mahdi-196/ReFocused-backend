#!/usr/bin/env python

"""
Script to run manual migrations.

Usage:
    python -m app.db.migrations.run_manual <migration_name>

Example:
    python -m app.db.migrations.run_manual add_study_set_indexes
"""

import os
import sys
import importlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migration(migration_name):
    """Run a specific manual migration."""
    # Get sync database URL for migration
    db_url = settings.DATABASE_URL
    if "sqlite+aiosqlite" in db_url:
        sync_url = db_url.replace("sqlite+aiosqlite", "sqlite")
    elif "postgresql+asyncpg" in db_url:
        sync_url = db_url.replace("postgresql+asyncpg", "postgresql")
    else:
        sync_url = db_url
    
    # Import the migration module
    try:
        migration_module = importlib.import_module(f"app.db.migrations.manual.{migration_name}")
    except ImportError as e:
        logger.error(f"Migration {migration_name} not found: {e}")
        sys.exit(1)
    
    # Create engine and session
    engine = create_engine(sync_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Run the migration
        logger.info(f"Running manual migration: {migration_name}")
        migration_module.upgrade()
        session.commit()
        logger.info(f"Manual migration {migration_name} completed successfully")
    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {str(e)}")
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error("Usage: python -m app.db.migrations.run_manual <migration_name>")
        sys.exit(1)
    
    migration_name = sys.argv[1]
    run_migration(migration_name) 