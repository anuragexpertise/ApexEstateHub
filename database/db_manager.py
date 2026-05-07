# database/db_manager.py
"""
Database Manager - Integrated with app/config.py
Uses SQLAlchemy for connection pooling (Aiven-compatible)
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from dotenv import load_dotenv

# Load config AFTER dotenv loads
from app.config import get_database_url, get_engine_options

load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Aiven-compatible database manager using SQLAlchemy connection pooling."""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._connect()
    
    def _connect(self):
        """Create engine with Aiven-optimized settings."""
        try:
            db_url = get_database_url()
            opts = get_engine_options()
            
            logger.info(f"Connecting to database: {db_url[:50]}...")
            
            # Create engine
            self.engine = create_engine(db_url, **opts)
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ Database connection established")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
    
    def test_connection(self):
        """Test if database is reachable."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return self._connect()  # Try reconnect
    
    @contextmanager
    def get_session(self):
        """Context manager for database sessions."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()
    
    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """
        Execute raw SQL query.
        Compatible with existing code using psycopg2-style interface.
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params or {})

                if fetch_one:
                    row = result.fetchone()
                    return dict(row._mapping) if row else None

                elif fetch_all:
                    rows = result.fetchall()
                    return [dict(row._mapping) for row in rows]

                return None

        except Exception as e:
            logger.error(f"Query error: {str(e)[:200]}")
            logger.error(f"Query: {query[:300]}")
            logger.error(f"Params: {params}")
            return None
    
    def execute_transaction(self, queries):
        """
        Execute multiple queries in a transaction.
        queries = [(sql, params), ...]
        """
        with self.get_session() as session:
            try:
                for query, params in queries:
                    session.execute(text(query), params or {})
                return True
            except Exception as e:
                logger.error(f"Transaction error: {e}")
                raise
    
    def close(self):
        """Dispose engine."""
        if self.engine:
            self.engine.dispose()


# Global instance
db = DatabaseManager()