from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Ensure data directory exists
os.makedirs("data/db", exist_ok=True)

SQLALCHEMY_DATABASE_URL = "sqlite:///./data/db/univideo.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def migrate_if_needed():
    """
    Auto-add columns if not exist - zero manual migration!
    Call this on app startup to ensure DB schema is up-to-date.
    """
    import sqlite3
    import logging
    
    logger = logging.getLogger(__name__)
    db_path = "./data/db/univideo.db"
    
    # Ensure DB file exists first
    if not os.path.exists(db_path):
        logger.info("Database not found, will be created by SQLAlchemy")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check and add task_state column
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'task_state' not in columns:
            logger.info("Adding 'task_state' column to jobs table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN task_state TEXT")
            conn.commit()
            logger.info("✅ Column 'task_state' added successfully")
        
        if 'login_mode' not in columns:
            logger.info("Adding 'login_mode' column to jobs table...")
            cursor.execute("ALTER TABLE jobs ADD COLUMN login_mode TEXT DEFAULT 'auto'")
            conn.commit()
            logger.info("✅ Column 'login_mode' added successfully")

        if 'video_id' not in columns:
             logger.info("Adding 'video_id' column to jobs table...")
             cursor.execute("ALTER TABLE jobs ADD COLUMN video_id TEXT")
             conn.commit()
             logger.info("✅ Column 'video_id' added successfully")
             
        if 'progress' not in columns:
             logger.info("Adding 'progress' column to jobs table...")
             cursor.execute("ALTER TABLE jobs ADD COLUMN progress INTEGER DEFAULT 0")
             conn.commit()
             logger.info("✅ Column 'progress' added successfully")

        else:
            logger.debug("Columns match schema")

        # Check and add accounts columns
        cursor.execute("PRAGMA table_info(accounts)")
        acc_columns = [col[1] for col in cursor.fetchall()]

        if 'credits_remaining' not in acc_columns:
             logger.info("Adding 'credits_remaining' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN credits_remaining INTEGER DEFAULT 0")
             conn.commit()
        
        if 'credits_last_checked' not in acc_columns:
             logger.info("Adding 'credits_last_checked' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN credits_last_checked TIMESTAMP")
             conn.commit()
             
        if 'credits_reset_at' not in acc_columns:
             logger.info("Adding 'credits_reset_at' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN credits_reset_at TIMESTAMP")
             conn.commit()
             
        if 'device_id' not in acc_columns:
             logger.info("Adding 'device_id' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN device_id TEXT")
             conn.commit()
             
        if 'token_status' not in acc_columns:
             logger.info("Adding 'token_status' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN token_status TEXT DEFAULT 'pending'")
             conn.commit()
             
        if 'token_captured_at' not in acc_columns:
             logger.info("Adding 'token_captured_at' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN token_captured_at TIMESTAMP")
             conn.commit()

        if 'token_expires_at' not in acc_columns:
             logger.info("Adding 'token_expires_at' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN token_expires_at TIMESTAMP")
             conn.commit()
             
        if 'access_token' not in acc_columns:
             logger.info("Adding 'access_token' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN access_token TEXT")
             conn.commit()

        if 'user_agent' not in acc_columns:
             logger.info("Adding 'user_agent' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN user_agent TEXT")
             conn.commit()

        if 'login_mode' not in acc_columns:
             logger.info("Adding 'login_mode' column to accounts...")
             cursor.execute("ALTER TABLE accounts ADD COLUMN login_mode TEXT DEFAULT 'auto'")
             conn.commit()

            
    except Exception as e:
        logger.error(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
