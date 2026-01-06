import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from config import load_config
from db_connection import get_db_cursor

def init_db():
    """Create message_history table if it doesn't exist"""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS message_history (
                conversation_key TEXT NOT NULL,
                messages JSONB NOT NULL,
                PRIMARY KEY (conversation_key)
            )
        """)
    # Auto-commits! ✅

def get_conversation_key(user_id_1: str, user_id_2: str) -> str:
    """
    Generate normalized conversation key (lower ID first)
    Example: get_conversation_key("9999", "1111") -> "1111_9999"
    """
    ids = sorted([str(user_id_1), str(user_id_2)])
    return f"{ids[0]}_{ids[1]}"

def save_message(user_id_1: str, user_id_2: str, from_id: str, text: str, language: str):
    """
    Save a message to full history
    Automatically cleans up old messages after saving
    
    Args:
        user_id_1: First user ID
        user_id_2: Second user ID
        from_id: ID of sender
        text: Message text
        language: Message language
    """
    key = get_conversation_key(user_id_1, user_id_2)
    
    with get_db_cursor() as cur:
        # Get existing messages
        cur.execute("SELECT messages FROM message_history WHERE conversation_key = %s", (key,))
        row = cur.fetchone()
        
        if row:
            messages = row[0]
        else:
            messages = []
        
        # Add new message with timestamp
        message = {
            "from": str(from_id),
            "text": text,
            "lang": language,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        messages.append(message)
        
        # Upsert messages
        cur.execute("""
            INSERT INTO message_history (conversation_key, messages)
            VALUES (%s, %s)
            ON CONFLICT (conversation_key)
            DO UPDATE SET messages = EXCLUDED.messages
        """, (key, Json(messages)))
    # Auto-commits! ✅
    
    # Cleanup old messages for this conversation
    cleanup_old_messages(user_id_1, user_id_2)

def get_messages(user_id_1: str, user_id_2: str, hours: Optional[int] = None) -> List[Dict]:
    """
    Get message history between two users
    
    Args:
        user_id_1: First user ID
        user_id_2: Second user ID
        hours: If specified, only return messages from last N hours
    
    Returns:
        List of messages (sorted oldest to newest)
    """
    try:
        key = get_conversation_key(user_id_1, user_id_2)
        
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT messages FROM message_history WHERE conversation_key = %s", (key,))
            row = cur.fetchone()
        
        if not row:
            return []
        
        messages = row[0]
        
        # Filter by time if specified
        if hours is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            messages = [
                msg for msg in messages
                if datetime.fromisoformat(msg['timestamp']) > cutoff
            ]
        
        return messages
    except Exception as e:
        print(f"Error getting message history: {e}")
        return []

def cleanup_old_messages(user_id_1: str, user_id_2: str):
    """
    Delete messages older than retention period for a specific conversation
    Retention period is configurable in config.json (default: 30 days)
    """
    try:
        config = load_config()
        retention_days = config.get('message_retention_days', 30)
        
        key = get_conversation_key(user_id_1, user_id_2)
        
        with get_db_cursor() as cur:
            # Get existing messages
            cur.execute("SELECT messages FROM message_history WHERE conversation_key = %s", (key,))
            row = cur.fetchone()
            
            if not row:
                return
            
            messages = row[0]
            
            # Filter out messages older than retention period
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            filtered_messages = [
                msg for msg in messages
                if datetime.fromisoformat(msg['timestamp']) > cutoff
            ]
            
            # Update if messages were deleted
            if len(filtered_messages) < len(messages):
                cur.execute("""
                    UPDATE message_history
                    SET messages = %s
                    WHERE conversation_key = %s
                """, (Json(filtered_messages), key))
                
                deleted_count = len(messages) - len(filtered_messages)
                print(f"Cleaned up {deleted_count} old messages for conversation {key}")
        # Auto-commits! ✅
        
    except Exception as e:
        print(f"Error cleaning up old messages: {e}")

def clear_history(user_id_1: str, user_id_2: str):
    """Clear all message history between two users"""
    key = get_conversation_key(user_id_1, user_id_2)
    
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM message_history WHERE conversation_key = %s", (key,))
    # Auto-commits! ✅

def get_all_conversations() -> Dict:
    """
    Get all conversations with full message history
    Returns dict: {conversation_key: messages_list}
    Used by dashboard for monitoring
    """
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT conversation_key, messages FROM message_history")
            rows = cur.fetchall()
            
            return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error getting all conversations: {e}")
        return {}

def get_message_count(user_id_1: str, user_id_2: str, hours: Optional[int] = None) -> int:
    """
    Get count of messages in a conversation
    
    Args:
        user_id_1: First user ID
        user_id_2: Second user ID
        hours: If specified, only count messages from last N hours
    
    Returns:
        Number of messages
    """
    messages = get_messages(user_id_1, user_id_2, hours=hours)
    return len(messages)

# Initialize database on import
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize message_history table: {e}")