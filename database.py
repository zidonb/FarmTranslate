import os
import json
import psycopg2
from psycopg2.extras import Json
from typing import Optional

def get_db_connection():
    """Get PostgreSQL connection from Railway DATABASE_URL"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL not found in environment variables")
    return psycopg2.connect(database_url)

def init_db():
    """Create tables if they don't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def load_data():
    """Load all users as a dictionary (compatible with old JSON approach)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT user_id, data FROM users")
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        # Convert to dictionary format
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error loading data: {e}")
        return {}

def save_data(data):
    """Save all users (bulk update - used for deletions)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Clear existing data
    cur.execute("DELETE FROM users")
    
    # Insert all users
    for user_id, user_data in data.items():
        cur.execute(
            "INSERT INTO users (user_id, data) VALUES (%s, %s)",
            (user_id, Json(user_data))
        )
    
    conn.commit()
    cur.close()
    conn.close()

def get_user(user_id: str) -> Optional[dict]:
    """Get user data by ID"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT data FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return row[0] if row else None
    except Exception as e:
        print(f"Error getting user {user_id}: {e}")
        return None

def save_user(user_id: str, user_data: dict):
    """Save or update user data"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Upsert (insert or update)
    cur.execute("""
        INSERT INTO users (user_id, data)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET data = EXCLUDED.data
    """, (user_id, Json(user_data)))
    
    conn.commit()
    cur.close()
    conn.close()

def get_all_users():
    """Get all users"""
    return load_data()

# Initialize database on import
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")