"""
Connection model — manager-worker relationships.
Database UNIQUE constraints prevent race conditions at the database level.
"""
import logging
from typing import Optional, Dict, List
from psycopg2 import errors as pg_errors
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


# Custom exceptions for constraint violations
class SlotOccupiedError(Exception):
    """Raised when a bot slot is already occupied by another worker."""
    pass


class WorkerAlreadyConnectedError(Exception):
    """Raised when a worker already has an active connection."""
    pass


def create(manager_id: int, worker_id: int, bot_slot: int) -> int:
    """
    Create a new connection. Database UNIQUE constraints prevent:
    - Two workers on the same bot slot for a manager
    - One worker connected to multiple managers

    Returns connection_id on success.
    Raises SlotOccupiedError or WorkerAlreadyConnectedError on constraint violation.
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO connections (manager_id, worker_id, bot_slot, status)
                VALUES (%s, %s, %s, 'active')
                RETURNING connection_id
            """, (manager_id, worker_id, bot_slot))
            connection_id = cur.fetchone()[0]

        logger.info(f"Connection created: id={connection_id}, manager={manager_id}, "
                     f"worker={worker_id}, slot={bot_slot}")
        return connection_id

    except pg_errors.UniqueViolation as e:
        error_msg = str(e)
        if 'idx_unique_manager_slot' in error_msg:
            raise SlotOccupiedError(
                f"Bot slot {bot_slot} already occupied for manager {manager_id}"
            )
        elif 'idx_unique_active_worker' in error_msg:
            raise WorkerAlreadyConnectedError(
                f"Worker {worker_id} already has an active connection"
            )
        else:
            raise


def disconnect(connection_id: int) -> Optional[Dict]:
    """
    Disconnect a connection (idempotent — safe to call twice).
    Returns the disconnected connection dict, or None if already disconnected.
    """
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE connections
            SET status = 'disconnected', disconnected_at = NOW()
            WHERE connection_id = %s AND status = 'active'
            RETURNING connection_id, manager_id, worker_id, bot_slot
        """, (connection_id,))
        row = cur.fetchone()

    if not row:
        return None

    logger.info(f"Connection disconnected: id={row[0]}, manager={row[1]}, "
                f"worker={row[2]}, slot={row[3]}")
    return {
        'connection_id': row[0],
        'manager_id': row[1],
        'worker_id': row[2],
        'bot_slot': row[3],
    }


def get_by_id(connection_id: int) -> Optional[Dict]:
    """Get connection by ID (any status)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT connection_id, manager_id, worker_id, bot_slot, status, "
            "connected_at, disconnected_at "
            "FROM connections WHERE connection_id = %s",
            (connection_id,)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'connection_id': row[0],
        'manager_id': row[1],
        'worker_id': row[2],
        'bot_slot': row[3],
        'status': row[4],
        'connected_at': row[5],
        'disconnected_at': row[6],
    }


def get_by_manager_and_slot(manager_id: int, bot_slot: int) -> Optional[Dict]:
    """Get active connection for a specific manager + bot slot."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT connection_id, manager_id, worker_id, bot_slot, connected_at "
            "FROM connections "
            "WHERE manager_id = %s AND bot_slot = %s AND status = 'active'",
            (manager_id, bot_slot)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'connection_id': row[0],
        'manager_id': row[1],
        'worker_id': row[2],
        'bot_slot': row[3],
        'connected_at': row[4],
    }


def get_active_for_manager(manager_id: int) -> List[Dict]:
    """Get all active connections for a manager."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT connection_id, manager_id, worker_id, bot_slot, connected_at "
            "FROM connections "
            "WHERE manager_id = %s AND status = 'active' "
            "ORDER BY bot_slot",
            (manager_id,)
        )
        rows = cur.fetchall()

    return [
        {
            'connection_id': r[0],
            'manager_id': r[1],
            'worker_id': r[2],
            'bot_slot': r[3],
            'connected_at': r[4],
        }
        for r in rows
    ]


def get_active_for_worker(worker_id: int) -> Optional[Dict]:
    """Get the active connection for a worker (workers can only have one)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT connection_id, manager_id, worker_id, bot_slot, connected_at "
            "FROM connections "
            "WHERE worker_id = %s AND status = 'active'",
            (worker_id,)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'connection_id': row[0],
        'manager_id': row[1],
        'worker_id': row[2],
        'bot_slot': row[3],
        'connected_at': row[4],
    }


def get_all_active() -> List[Dict]:
    """Get all active connections (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT c.connection_id, c.manager_id, c.worker_id, c.bot_slot, c.connected_at, "
            "mu.telegram_name as manager_name, wu.telegram_name as worker_name "
            "FROM connections c "
            "JOIN users mu ON c.manager_id = mu.user_id "
            "JOIN users wu ON c.worker_id = wu.user_id "
            "WHERE c.status = 'active' "
            "ORDER BY c.connected_at DESC"
        )
        rows = cur.fetchall()

    return [
        {
            'connection_id': r[0],
            'manager_id': r[1],
            'worker_id': r[2],
            'bot_slot': r[3],
            'connected_at': r[4],
            'manager_name': r[5],
            'worker_name': r[6],
        }
        for r in rows
    ]
