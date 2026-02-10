"""
Usage model — message counting and free-tier limits.
Tracks per-manager (not per-user) since billing is on the manager.
"""
import logging
from typing import Optional, Dict
from config import load_config
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def get(manager_id: int) -> Optional[Dict]:
    """Get usage record for a manager. Returns None if no record exists."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT manager_id, messages_sent, is_blocked, first_message_at, last_message_at "
            "FROM usage_tracking WHERE manager_id = %s",
            (manager_id,)
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        'manager_id': row[0],
        'messages_sent': row[1],
        'is_blocked': row[2],
        'first_message_at': row[3],
        'last_message_at': row[4],
    }


def is_blocked(manager_id: int) -> bool:
    """Check if manager has reached message limit and is blocked."""
    config = load_config()

    # Whitelisted test users bypass limits
    if config.get('testing_mode', False):
        test_ids = config.get('test_user_ids', [])
        if str(manager_id) in test_ids:
            return False

    usage = get(manager_id)
    if not usage:
        return False

    return usage.get('is_blocked', False)


def increment(manager_id: int) -> bool:
    """
    Atomically increment message count and check limit.
    Returns True if message is allowed, False if limit reached.
    Ensures row exists, then increments in a single transaction.
    """
    config = load_config()
    free_limit = config.get('free_message_limit', 100)
    enforce_limits = config.get('enforce_limits', False)

    if not enforce_limits:
        return True

    # Whitelisted test users bypass limits
    if config.get('testing_mode', False):
        test_ids = config.get('test_user_ids', [])
        if str(manager_id) in test_ids:
            return True

    with get_db_cursor() as cur:
        # Ensure row exists
        cur.execute("""
            INSERT INTO usage_tracking (manager_id, messages_sent, is_blocked, first_message_at)
            VALUES (%s, 0, FALSE, NOW())
            ON CONFLICT (manager_id) DO NOTHING
        """, (manager_id,))

        # Atomic increment
        cur.execute("""
            UPDATE usage_tracking
            SET messages_sent = messages_sent + 1,
                last_message_at = NOW()
            WHERE manager_id = %s
            RETURNING messages_sent, is_blocked
        """, (manager_id,))

        row = cur.fetchone()
        if not row:
            return True

        messages_sent, currently_blocked = row

        if currently_blocked:
            return False

        # Check if just hit the limit
        if messages_sent >= free_limit:
            cur.execute(
                "UPDATE usage_tracking SET is_blocked = TRUE WHERE manager_id = %s",
                (manager_id,)
            )
            return False

        return True


def reset(manager_id: int):
    """Reset usage counter (admin function)."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE usage_tracking SET messages_sent = 0, is_blocked = FALSE "
            "WHERE manager_id = %s",
            (manager_id,)
        )

    logger.info(f"Usage reset: manager={manager_id}")


def block(manager_id: int):
    """Block a manager (mark as exceeding free tier)."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE usage_tracking SET is_blocked = TRUE WHERE manager_id = %s",
            (manager_id,)
        )

    logger.info(f"Usage blocked: manager={manager_id}")


def unblock(manager_id: int):
    """Unblock a manager (e.g. after subscribing)."""
    with get_db_cursor() as cur:
        cur.execute(
            "UPDATE usage_tracking SET is_blocked = FALSE WHERE manager_id = %s",
            (manager_id,)
        )

    logger.info(f"Usage unblocked: manager={manager_id}")


def get_all() -> list:
    """Get all usage records (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute(
            "SELECT ut.manager_id, ut.messages_sent, ut.is_blocked, "
            "ut.first_message_at, ut.last_message_at, u.telegram_name "
            "FROM usage_tracking ut "
            "JOIN users u ON ut.manager_id = u.user_id "
            "ORDER BY ut.messages_sent DESC"
        )
        rows = cur.fetchall()

    return [
        {
            'manager_id': r[0],
            'messages_sent': r[1],
            'is_blocked': r[2],
            'first_message_at': r[3],
            'last_message_at': r[4],
            'telegram_name': r[5],
        }
        for r in rows
    ]


def get_stats() -> Dict:
    """Get aggregated usage statistics (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total_tracked,
                COALESCE(SUM(messages_sent), 0) as total_messages,
                COUNT(*) FILTER (WHERE is_blocked = TRUE) as blocked_count,
                COUNT(*) FILTER (WHERE is_blocked = FALSE) as active_count
            FROM usage_tracking
        """)
        row = cur.fetchone()

    return {
        'total_users_tracked': row[0],
        'total_messages_sent': row[1],
        'blocked_users': row[2],
        'active_users': row[3],
    }
