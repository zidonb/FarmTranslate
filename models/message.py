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
