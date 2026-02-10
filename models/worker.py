"""
Worker model — worker-specific data.
"""
import logging
from typing import Optional, Dict
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def get_by_id(worker_id: int) -> Optional[Dict]:
    """Get active worker by ID. Returns None if not found or soft-deleted."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT worker_id, created_at "
            "FROM workers WHERE worker_id = %s AND deleted_at IS NULL",
            (worker_id,)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'worker_id': row[0],
        'created_at': row[1],
    }


def create(worker_id: int):
    """Create a worker record. User must already exist in users table."""
    with get_db_cursor() as cur:
        cur.execute(
            "INSERT INTO workers (worker_id) VALUES (%s) "
            "ON CONFLICT (worker_id) DO UPDATE SET deleted_at = NULL",
            (worker_id,)
        )

    logger.info(f"Worker created: worker_id={worker_id}")


def get_all_active() -> list:
    """Get all active workers with their connection info (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT w.worker_id, u.telegram_name, u.language, u.gender, w.created_at, "
            "c.manager_id, c.bot_slot "
            "FROM workers w "
            "JOIN users u ON w.worker_id = u.user_id "
            "LEFT JOIN connections c ON w.worker_id = c.worker_id AND c.status = 'active' "
            "WHERE w.deleted_at IS NULL "
            "ORDER BY w.created_at DESC"
        )
        rows = cur.fetchall()

    return [
        {
            'worker_id': r[0],
            'telegram_name': r[1],
            'language': r[2],
            'gender': r[3],
            'created_at': r[4],
            'manager_id': r[5],
            'bot_slot': r[6],
        }
        for r in rows
    ]


def soft_delete(worker_id: int):
    """Soft-delete a worker (preserves history)."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE workers SET deleted_at = NOW() WHERE worker_id = %s AND deleted_at IS NULL",
            (worker_id,)
        )

    logger.info(f"Worker soft-deleted: worker_id={worker_id}")
