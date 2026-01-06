import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from db_connection import get_db_cursor

def init_tasks_table():
    """Create tasks table if it doesn't exist"""
    with get_db_cursor() as cur:
        # Create tasks table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                manager_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                description TEXT NOT NULL,
                description_translated TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """)
        
        # Create indexes for faster queries
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_manager_status 
            ON tasks(manager_id, status)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_worker_status 
            ON tasks(worker_id, status)
        """)
    # Auto-commits all 3 statements! ✅
    print("✅ Tasks table initialized")

def create_task(manager_id: str, worker_id: str, description: str, description_translated: str) -> int:
    """
    Create a new task and return task ID
    
    Args:
        manager_id: Telegram ID of manager
        worker_id: Telegram ID of worker
        description: Task description in manager's language
        description_translated: Task description in worker's language
    
    Returns:
        int: Task ID (auto-incremented)
    """
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO tasks (manager_id, worker_id, description, description_translated)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (manager_id, worker_id, description, description_translated))
        
        task_id = cur.fetchone()[0]
    # Auto-commits! ✅
    
    print(f"✅ Task created: ID={task_id}, Manager={manager_id}, Worker={worker_id}")
    return task_id

def complete_task(task_id: int) -> Optional[Dict]:
    """
    Mark task as completed and return task details
    
    Args:
        task_id: Task ID to complete
    
    Returns:
        dict with task details if successful, None if task not found or already completed
        {
            'id': int,
            'manager_id': str,
            'worker_id': str,
            'description': str,
            'description_translated': str,
            'completed_at': datetime
        }
    """
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE tasks
            SET status = 'completed', completed_at = NOW()
            WHERE id = %s AND status = 'pending'
            RETURNING id, manager_id, worker_id, description, description_translated, completed_at
        """, (task_id,))
        
        result = cur.fetchone()
    # Auto-commits! ✅
    
    if result:
        task_dict = {
            'id': result[0],
            'manager_id': result[1],
            'worker_id': result[2],
            'description': result[3],
            'description_translated': result[4],
            'completed_at': result[5]
        }
        print(f"✅ Task completed: ID={task_id}")
        return task_dict
    else:
        print(f"⚠️ Task not found or already completed: ID={task_id}")
        return None

def get_manager_tasks(manager_id: str, status: Optional[str] = None, limit_hours: Optional[int] = None) -> List[Dict]:
    """
    Get tasks for a manager (optionally filtered by status and time)
    
    Args:
        manager_id: Telegram ID of manager
        status: Optional filter ('pending', 'completed', or None for all)
        limit_hours: Optional filter for tasks created in last N hours (e.g., 24 for today)
    
    Returns:
        List of task dicts, ordered by created_at DESC
        [
            {
                'id': int,
                'description': str,
                'status': str,
                'created_at': datetime,
                'completed_at': datetime or None,
                'worker_id': str
            },
            ...
        ]
    """
    query = """
        SELECT id, description, status, created_at, completed_at, worker_id
        FROM tasks
        WHERE manager_id = %s
    """
    params = [manager_id]
    
    # Add status filter
    if status:
        query += " AND status = %s"
        params.append(status)
    
    # Add time filter
    if limit_hours:
        query += " AND created_at > NOW() - INTERVAL '%s hours'"
        params.append(limit_hours)
    
    query += " ORDER BY created_at DESC"
    
    with get_db_cursor(commit=False) as cur:  # ✅ Read-only
        cur.execute(query, params)
        rows = cur.fetchall()
    
    tasks_list = []
    for row in rows:
        tasks_list.append({
            'id': row[0],
            'description': row[1],
            'status': row[2],
            'created_at': row[3],
            'completed_at': row[4],
            'worker_id': row[5]
        })
    
    return tasks_list

def get_worker_tasks(worker_id: str, status: Optional[str] = None, limit_hours: Optional[int] = None) -> List[Dict]:
    """
    Get tasks for a worker (optionally filtered by status and time)
    
    Args:
        worker_id: Telegram ID of worker
        status: Optional filter ('pending', 'completed', or None for all)
        limit_hours: Optional filter for tasks created in last N hours
    
    Returns:
        List of task dicts, ordered by created_at DESC
        [
            {
                'id': int,
                'description': str (in worker's language),
                'status': str,
                'created_at': datetime,
                'completed_at': datetime or None,
                'manager_id': str
            },
            ...
        ]
    """
    query = """
        SELECT id, description_translated, status, created_at, completed_at, manager_id
        FROM tasks
        WHERE worker_id = %s
    """
    params = [worker_id]
    
    # Add status filter
    if status:
        query += " AND status = %s"
        params.append(status)
    
    # Add time filter
    if limit_hours:
        query += " AND created_at > NOW() - INTERVAL '%s hours'"
        params.append(limit_hours)
    
    query += " ORDER BY created_at DESC"
    
    with get_db_cursor(commit=False) as cur:  # ✅ Read-only
        cur.execute(query, params)
        rows = cur.fetchall()
    
    tasks_list = []
    for row in rows:
        tasks_list.append({
            'id': row[0],
            'description': row[1],  # Translated version for worker
            'status': row[2],
            'created_at': row[3],
            'completed_at': row[4],
            'manager_id': row[5]
        })
    
    return tasks_list

def get_task_by_id(task_id: int) -> Optional[Dict]:
    """
    Get a single task by ID
    
    Args:
        task_id: Task ID
    
    Returns:
        Task dict or None if not found
    """
    with get_db_cursor(commit=False) as cur:  # ✅ Read-only
        cur.execute("""
            SELECT id, manager_id, worker_id, description, description_translated, 
                   status, created_at, completed_at
            FROM tasks
            WHERE id = %s
        """, (task_id,))
        
        row = cur.fetchone()
    
    if row:
        return {
            'id': row[0],
            'manager_id': row[1],
            'worker_id': row[2],
            'description': row[3],
            'description_translated': row[4],
            'status': row[5],
            'created_at': row[6],
            'completed_at': row[7]
        }
    return None

def delete_task(task_id: int) -> bool:
    """
    Delete a task (admin function)
    
    Args:
        task_id: Task ID to delete
    
    Returns:
        bool: True if deleted, False if not found
    """
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        deleted = cur.rowcount > 0
    # Auto-commits! ✅
    
    if deleted:
        print(f"🗑️ Task deleted: ID={task_id}")
    return deleted

def clear_tasks_for_conversation(manager_id: str, worker_id: str) -> int:
    """
    Clear all tasks for a specific manager-worker pair (admin function)
    
    Args:
        manager_id: Telegram ID of manager
        worker_id: Telegram ID of worker
    
    Returns:
        int: Number of tasks deleted
    """
    with get_db_cursor() as cur:
        cur.execute("""
            DELETE FROM tasks 
            WHERE manager_id = %s AND worker_id = %s
        """, (manager_id, worker_id))
        
        deleted_count = cur.rowcount
    # Auto-commits! ✅
    
    print(f"🗑️ Cleared {deleted_count} tasks for manager={manager_id}, worker={worker_id}")
    return deleted_count


def get_task_stats(manager_id: str) -> Dict:
    """
    Get task statistics for a manager
    
    Args:
        manager_id: Telegram ID of manager
    
    Returns:
        dict with stats:
        {
            'total': int,
            'pending': int,
            'completed': int,
            'completed_today': int
        }
    """
    with get_db_cursor(commit=False) as cur:  # ✅ Read-only
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'completed' AND completed_at > NOW() - INTERVAL '24 hours') as completed_today
            FROM tasks
            WHERE manager_id = %s
        """, (manager_id,))
        
        row = cur.fetchone()
    
    return {
        'total': row[0],
        'pending': row[1],
        'completed': row[2],
        'completed_today': row[3]
    }

# Initialize table on import
try:
    init_tasks_table()
except Exception as e:
    print(f"⚠️ Warning: Could not initialize tasks table: {e}")