import os
import psycopg2
from datetime import datetime
from typing import List, Dict, Optional
from db_connection import get_db_cursor


def init_feedback_table():
    """Create feedback table if it doesn't exist"""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                telegram_user_id TEXT NOT NULL,
                user_name TEXT,
                username TEXT,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                status TEXT DEFAULT 'unread'
            )
        """)
    # Auto-commits! ✅

def save_feedback(telegram_user_id: str, user_name: str, username: Optional[str], message: str):
    """Save feedback to database"""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO feedback (telegram_user_id, user_name, username, message)
            VALUES (%s, %s, %s, %s)
        """, (telegram_user_id, user_name, username, message))
    # Auto-commits! ✅

def get_all_feedback(limit: int = 100) -> List[Dict]:
    """Get all feedback (for dashboard)"""
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ commit=False for read-only queries
            cur.execute("""
                SELECT id, telegram_user_id, user_name, username, message, created_at, status
                FROM feedback
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            
            rows = cur.fetchall()
        
        feedback_list = []
        for row in rows:
            feedback_list.append({
                'id': row[0],
                'telegram_user_id': row[1],
                'user_name': row[2],
                'username': row[3],
                'message': row[4],
                'created_at': row[5],
                'status': row[6]
            })
        
        return feedback_list
    except Exception as e:
        print(f"Error getting feedback: {e}")
        return []

def mark_as_read(feedback_id: int):
    """Mark feedback as read"""
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE feedback
            SET status = 'read'
            WHERE id = %s
        """, (feedback_id,))
    # Auto-commits! ✅

# Initialize table on import
try:
    init_feedback_table()
except Exception as e:
    print(f"Warning: Could not initialize feedback table: {e}")