"""
Feedback model — user feedback storage.
"""
import logging
from typing import List, Dict, Optional
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def save(user_id: int, telegram_name: str = None, username: str = None, message: str = ''):
    """Save feedback to database."""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO feedback (user_id, telegram_name, username, message)
            VALUES (%s, %s, %s, %s)
        """, (user_id, telegram_name, username, message))

    logger.info(f"Feedback saved from user={user_id}")


def get_all(limit: int = 100) -> List[Dict]:
    """Get all feedback ordered by newest first (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT feedback_id, user_id, telegram_name, username, message, created_at, status
            FROM feedback
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()

    return [
        {
            'feedback_id': r[0],
            'user_id': r[1],
            'telegram_name': r[2],
            'username': r[3],
            'message': r[4],
            'created_at': r[5],
            'status': r[6],
        }
        for r in rows
    ]


def mark_as_read(feedback_id: int):
    """Mark feedback as read."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE feedback SET status = 'read' WHERE feedback_id = %s",
            (feedback_id,)
        )
