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


def soft_delete(worker_id: int):
    """Soft-delete a worker (preserves history)."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE workers SET deleted_at = NOW() WHERE worker_id = %s AND deleted_at IS NULL",
            (worker_id,)
        )

    logger.info(f"Worker soft-deleted: worker_id={worker_id}")
