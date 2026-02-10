"""
Message model — communication history.
Replaces both message_history.py (full history) and translation_msg_context.py (sliding window).
Messages belong to connections, not directly to user pairs.
"""
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from config import load_config
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def save(connection_id: int, sender_id: int, original_text: str, translated_text: str):
    """Save a translated message."""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO messages (connection_id, sender_id, original_text, translated_text)
            VALUES (%s, %s, %s, %s)
        """, (connection_id, sender_id, original_text, translated_text))

    # Probabilistic cleanup (10% of saves)
    if random.random() < 0.1:
        cleanup_expired()


def get_recent(connection_id: int, hours: int = 24) -> List[Dict]:
    """
    Get messages for a connection from the last N hours.
    Used for /daily action items.
    """
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT message_id, sender_id, original_text, translated_text, sent_at
            FROM messages
            WHERE connection_id = %s
              AND sent_at > NOW() - INTERVAL '%s hours'
            ORDER BY sent_at ASC
        """, (connection_id, hours))
        rows = cur.fetchall()

    return [
        {
            'message_id': r[0],
            'sender_id': r[1],
            'original_text': r[2],
            'translated_text': r[3],
            'sent_at': r[4],
            # 'from' and 'text' keys for backward compatibility with translator.py
            'from': str(r[1]),
            'text': r[2],
        }
        for r in rows
    ]


def get_translation_context(connection_id: int, limit: int = 3) -> List[Dict]:
    """
    Get last N messages for translation context (sliding window).
    Replaces translation_msg_context.py's get_conversation_history().
    Returns format expected by translator.py.
    """
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT sender_id, original_text, translated_text, sent_at
            FROM messages
            WHERE connection_id = %s
            ORDER BY sent_at DESC
            LIMIT %s
        """, (connection_id, limit))
        rows = cur.fetchall()

    # Reverse to oldest-first (translator expects chronological order)
    rows = list(reversed(rows))

    return [
        {
            'from': str(r[0]),
            'text': r[1],
            'translated_text': r[2],
            'timestamp': r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]


def get_for_connection(connection_id: int, limit: int = 500) -> List[Dict]:
    """
    Get all messages for a connection (for dashboard detail page).
    Returns chronological order with sender info.
    """
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT message_id, sender_id, original_text, translated_text, sent_at
            FROM messages
            WHERE connection_id = %s
            ORDER BY sent_at ASC
            LIMIT %s
        """, (connection_id, limit))
        rows = cur.fetchall()

    return [
        {
            'message_id': r[0],
            'sender_id': r[1],
            'original_text': r[2],
            'translated_text': r[3],
            'sent_at': r[4],
            'from': str(r[1]),
            'text': r[2],
        }
        for r in rows
    ]


def delete_for_connection(connection_id: int):
    """Delete all messages for a connection (admin action)."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM messages WHERE connection_id = %s", (connection_id,))
        deleted = cur.rowcount

    if deleted > 0:
        logger.info(f"Deleted {deleted} messages for connection={connection_id}")


def get_recent_across_connections(limit_per_connection: int = 10) -> List[Dict]:
    """
    Get recent messages across all active connections (for dashboard main page).
    Returns messages grouped by connection_id with manager/worker metadata.
    """
    with get_db_cursor(commit=False) as cur:
        # Get last N messages per active connection using a lateral join
        cur.execute("""
            SELECT c.connection_id, c.manager_id, c.worker_id, c.bot_slot,
                   m.message_id, m.sender_id, m.original_text, m.translated_text, m.sent_at,
                   mu.telegram_name as manager_name, wu.telegram_name as worker_name
            FROM connections c
            JOIN users mu ON c.manager_id = mu.user_id
            JOIN users wu ON c.worker_id = wu.user_id
            JOIN LATERAL (
                SELECT message_id, sender_id, original_text, translated_text, sent_at
                FROM messages
                WHERE messages.connection_id = c.connection_id
                ORDER BY sent_at DESC
                LIMIT %s
            ) m ON true
            WHERE c.status = 'active'
            ORDER BY c.connection_id, m.sent_at ASC
        """, (limit_per_connection,))
        rows = cur.fetchall()

    # Group by connection
    from collections import OrderedDict
    connections = OrderedDict()
    for r in rows:
        conn_id = r[0]
        if conn_id not in connections:
            connections[conn_id] = {
                'connection_id': conn_id,
                'manager_id': r[1],
                'worker_id': r[2],
                'bot_slot': r[3],
                'manager_name': r[9],
                'worker_name': r[10],
                'messages': [],
            }
        connections[conn_id]['messages'].append({
            'message_id': r[4],
            'sender_id': r[5],
            'original_text': r[6],
            'translated_text': r[7],
            'sent_at': r[8],
        })

    return list(connections.values())


def get_total_count() -> int:
    """Get total message count across all connections (for dashboard stats)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute("SELECT COUNT(*) FROM messages")
        return cur.fetchone()[0]


def get_count(connection_id: int, hours: Optional[int] = None) -> int:
    """Get message count for a connection, optionally limited by time."""
    if hours:
        with get_db_cursor(commit=False) as cur:
            cur.execute("""
                SELECT COUNT(*) FROM messages
                WHERE connection_id = %s
                  AND sent_at > NOW() - INTERVAL '%s hours'
            """, (connection_id, hours))
            return cur.fetchone()[0]
    else:
        with get_db_cursor(commit=False) as cur:
            cur.execute(
                "SELECT COUNT(*) FROM messages WHERE connection_id = %s",
                (connection_id,)
            )
            return cur.fetchone()[0]


def cleanup_expired():
    """Delete messages older than retention period."""
    try:
        config = load_config()
        retention_days = config.get('message_retention_days', 30)

        with get_db_cursor() as cur:
            cur.execute(
                "DELETE FROM messages WHERE sent_at < NOW() - INTERVAL '%s days'",
                (retention_days,)
            )
            deleted = cur.rowcount

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired messages (>{retention_days} days old)")
    except Exception as e:
        logger.warning(f"Error cleaning up expired messages: {e}")
