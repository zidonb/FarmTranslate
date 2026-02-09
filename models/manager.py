"""
Manager model — manager-specific data and role detection.
"""
import logging
from typing import Optional, Dict
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def get_by_id(manager_id: int) -> Optional[Dict]:
    """Get active manager by ID. Returns None if not found or soft-deleted."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT manager_id, code, industry, created_at "
            "FROM managers WHERE manager_id = %s AND deleted_at IS NULL",
            (manager_id,)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'manager_id': row[0],
        'code': row[1],
        'industry': row[2],
        'created_at': row[3],
    }


def get_by_code(code: str) -> Optional[Dict]:
    """Find active manager by invitation code (e.g. 'BRIDGE-12345')."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT manager_id, code, industry, created_at "
            "FROM managers WHERE code = %s AND deleted_at IS NULL",
            (code,)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'manager_id': row[0],
        'code': row[1],
        'industry': row[2],
        'created_at': row[3],
    }


def create(manager_id: int, code: str, industry: str):
    """Create a manager record. User must already exist in users table."""
    with get_db_cursor() as cur:
        cur.execute(
            "INSERT INTO managers (manager_id, code, industry) VALUES (%s, %s, %s)",
            (manager_id, code, industry)
        )

    logger.info(f"Manager created: manager_id={manager_id}, code={code}, industry={industry}")


def soft_delete(manager_id: int):
    """Soft-delete a manager (preserves history)."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE managers SET deleted_at = NOW() WHERE manager_id = %s AND deleted_at IS NULL",
            (manager_id,)
        )

    logger.info(f"Manager soft-deleted: manager_id={manager_id}")


def get_role(user_id: int) -> Optional[str]:
    """
    Determine user's role: 'manager', 'worker', or None.
    Checks managers table first, then workers.
    """
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT 1 FROM managers WHERE manager_id = %s AND deleted_at IS NULL",
            (user_id,)
        )
        if cur.fetchone():
            return 'manager'

        cur.execute(
            "SELECT 1 FROM workers WHERE worker_id = %s AND deleted_at IS NULL",
            (user_id,)
        )
        if cur.fetchone():
            return 'worker'

    return None


def code_exists(code: str) -> bool:
    """Check if an invitation code is already in use by an active manager."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT 1 FROM managers WHERE code = %s AND deleted_at IS NULL",
            (code,)
        )
        return cur.fetchone() is not None


def get_all_active() -> list:
    """Get all active managers (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT m.manager_id, m.code, m.industry, m.created_at, u.telegram_name, u.language "
            "FROM managers m JOIN users u ON m.manager_id = u.user_id "
            "WHERE m.deleted_at IS NULL "
            "ORDER BY m.created_at DESC"
        )
        rows = cur.fetchall()

    return [
        {
            'manager_id': r[0],
            'code': r[1],
            'industry': r[2],
            'created_at': r[3],
            'telegram_name': r[4],
            'language': r[5],
        }
        for r in rows
    ]
