"""
User model — identity layer (role-agnostic).
Every person in the system has exactly one row in the users table.
"""
import logging
from typing import Optional, Dict
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def get_by_id(user_id: int) -> Optional[Dict]:
    """Get user by Telegram user ID. Returns None if not found."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT user_id, telegram_name, language, gender, created_at, updated_at "
            "FROM users WHERE user_id = %s",
            (user_id,)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'user_id': row[0],
        'telegram_name': row[1],
        'language': row[2],
        'gender': row[3],
        'created_at': row[4],
        'updated_at': row[5],
    }


def create(user_id: int, telegram_name: str = None, language: str = 'English', gender: str = None):
    """
    Create a new user. Uses ON CONFLICT to handle re-registration gracefully
    (updates existing record if user already exists).
    """
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO users (user_id, telegram_name, language, gender)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                telegram_name = EXCLUDED.telegram_name,
                language = EXCLUDED.language,
                gender = EXCLUDED.gender,
                updated_at = NOW()
        """, (user_id, telegram_name, language, gender))

    logger.info(f"User created/updated: user_id={user_id}")


def update(user_id: int, **fields):
    """
    Update specific fields on a user record.
    Usage: user_model.update(123, language='Hebrew', telegram_name='Yossi')
    """
    if not fields:
        return

    allowed = {'telegram_name', 'language', 'gender'}
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return

    set_clause = ", ".join(f"{k} = %s" for k in filtered)
    values = list(filtered.values()) + [user_id]

    with get_db_cursor() as cur:
        cur.execute(
            f"UPDATE users SET {set_clause}, updated_at = NOW() WHERE user_id = %s",
            values
        )


def delete(user_id: int):
    """Hard delete user. Cascades to managers/workers via FK."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

    logger.info(f"User deleted: user_id={user_id}")


def get_all() -> list:
    """Get all users (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT user_id, telegram_name, language, gender, created_at "
            "FROM users ORDER BY created_at DESC"
        )
        rows = cur.fetchall()

    return [
        {
            'user_id': r[0],
            'telegram_name': r[1],
            'language': r[2],
            'gender': r[3],
            'created_at': r[4],
        }
        for r in rows
    ]
