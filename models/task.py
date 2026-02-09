"""
Task model — task assignments tied to connections.
"""
import logging
from typing import Optional, Dict, List
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def create(connection_id: int, description: str, description_translated: str = None) -> int:
    """Create a new task. Returns task_id."""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO tasks (connection_id, description, description_translated)
            VALUES (%s, %s, %s)
            RETURNING task_id
        """, (connection_id, description, description_translated))
        task_id = cur.fetchone()[0]

    logger.info(f"Task created: id={task_id}, connection={connection_id}")
    return task_id


def complete(task_id: int) -> Optional[Dict]:
    """
    Mark task as completed (idempotent).
    Returns task dict if successfully completed, None if not found or already completed.
    """
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE tasks
            SET status = 'completed', completed_at = NOW()
            WHERE task_id = %s AND status = 'pending'
            RETURNING task_id, connection_id, description, description_translated, completed_at
        """, (task_id,))
        row = cur.fetchone()

    if not row:
        return None

    logger.info(f"Task completed: id={task_id}")
    return {
        'task_id': row[0],
        'connection_id': row[1],
        'description': row[2],
        'description_translated': row[3],
        'completed_at': row[4],
    }


def get_by_id(task_id: int) -> Optional[Dict]:
    """Get a single task by ID."""
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT task_id, connection_id, description, description_translated,
                   status, created_at, completed_at
            FROM tasks WHERE task_id = %s
        """, (task_id,))
        row = cur.fetchone()

    if not row:
        return None

    return {
        'task_id': row[0],
        'connection_id': row[1],
        'description': row[2],
        'description_translated': row[3],
        'status': row[4],
        'created_at': row[5],
        'completed_at': row[6],
    }


def get_manager_tasks(manager_id: int, status: str = None, limit_hours: int = None) -> List[Dict]:
    """
    Get tasks for a manager across all their connections.
    Joins through connections table to resolve worker_id for grouping.
    """
    query = """
        SELECT t.task_id, t.description, t.status, t.created_at, t.completed_at,
               c.worker_id, t.connection_id
        FROM tasks t
        JOIN connections c ON t.connection_id = c.connection_id
        WHERE c.manager_id = %s
    """
    params: list = [manager_id]

    if status:
        query += " AND t.status = %s"
        params.append(status)

    if limit_hours:
        if status == 'completed':
            query += " AND t.completed_at > NOW() - INTERVAL '%s hours'"
        else:
            query += " AND t.created_at > NOW() - INTERVAL '%s hours'"
        params.append(limit_hours)

    query += " ORDER BY t.created_at DESC"

    with get_db_cursor(commit=False) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            'task_id': r[0],
            'description': r[1],
            'status': r[2],
            'created_at': r[3],
            'completed_at': r[4],
            'worker_id': r[5],
            'connection_id': r[6],
        }
        for r in rows
    ]


def get_worker_tasks(worker_id: int, status: str = None, limit_hours: int = None) -> List[Dict]:
    """
    Get tasks for a worker across all their connections.
    Returns description_translated (worker's language) as 'description'.
    """
    query = """
        SELECT t.task_id, t.description_translated, t.status, t.created_at, t.completed_at,
               c.manager_id, t.connection_id
        FROM tasks t
        JOIN connections c ON t.connection_id = c.connection_id
        WHERE c.worker_id = %s
    """
    params: list = [worker_id]

    if status:
        query += " AND t.status = %s"
        params.append(status)

    if limit_hours:
        if status == 'completed':
            query += " AND t.completed_at > NOW() - INTERVAL '%s hours'"
        else:
            query += " AND t.created_at > NOW() - INTERVAL '%s hours'"
        params.append(limit_hours)

    query += " ORDER BY t.created_at DESC"

    with get_db_cursor(commit=False) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            'task_id': r[0],
            'description': r[1],  # translated version for worker
            'status': r[2],
            'created_at': r[3],
            'completed_at': r[4],
            'manager_id': r[5],
            'connection_id': r[6],
        }
        for r in rows
    ]


def get_stats(manager_id: int) -> Dict:
    """Get task statistics for a manager (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE t.status = 'pending') as pending,
                COUNT(*) FILTER (WHERE t.status = 'completed') as completed,
                COUNT(*) FILTER (WHERE t.status = 'completed'
                    AND t.completed_at > NOW() - INTERVAL '24 hours') as completed_today
            FROM tasks t
            JOIN connections c ON t.connection_id = c.connection_id
            WHERE c.manager_id = %s
        """, (manager_id,))
        row = cur.fetchone()

    return {
        'total': row[0],
        'pending': row[1],
        'completed': row[2],
        'completed_today': row[3],
    }
