import os
import json
import psycopg2
from psycopg2.extras import Json
from typing import Optional
from db_connection import get_db_cursor


def init_db():
    """Create tables if they don't exist"""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                data JSONB NOT NULL
            )
        """)
    # Auto-commits! ✅

def load_data():
    """Load all users as a dictionary (compatible with old JSON approach)"""
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT user_id, data FROM users")
            rows = cur.fetchall()
            
            # Convert to dictionary format
            return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error loading data: {e}")
        return {}

def save_data(data):
    """Save all users (bulk update - used for deletions)"""
    with get_db_cursor() as cur:
        # Clear existing data
        cur.execute("DELETE FROM users")
        
        # Insert all users
        for user_id, user_data in data.items():
            cur.execute(
                "INSERT INTO users (user_id, data) VALUES (%s, %s)",
                (user_id, Json(user_data))
            )
    # Auto-commits all changes as one transaction! ✅

def get_user(user_id: str) -> Optional[dict]:
    """Get user data by ID"""
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT data FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            
            return row[0] if row else None
    except Exception as e:
        print(f"Error getting user {user_id}: {e}")
        return None

def save_user(user_id: str, user_data: dict):
    """Save or update user data"""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO users (user_id, data)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET data = EXCLUDED.data
        """, (user_id, Json(user_data)))
    # Auto-commits! ✅

def get_all_users():
    """Get all users"""
    return load_data()

# Initialize database on import
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")