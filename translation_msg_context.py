import os
import json
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from typing import List, Dict, Optional
from db_connection import get_db_cursor
from datetime import datetime, timezone

def init_db():
    """Create conversations table if it doesn't exist"""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_key TEXT PRIMARY KEY,
                messages JSONB NOT NULL
            )
        """)
    # Auto-commits! ✅

def load_conversations():
    """Load all conversations as a dictionary (compatible with old JSON approach)"""
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT conversation_key, messages FROM conversations")
            rows = cur.fetchall()
            
            # Convert to dictionary format
            return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error loading conversations: {e}")
        return {}

def save_conversations(data):
    """Save all conversations (bulk update)"""
    with get_db_cursor() as cur:
        # Clear existing data
        cur.execute("DELETE FROM conversations")
        
        # Insert all conversations
        for conv_key, messages in data.items():
            cur.execute(
                "INSERT INTO conversations (conversation_key, messages) VALUES (%s, %s)",
                (conv_key, Json(messages))
            )
    # Auto-commits all changes together! ✅

def get_conversation_key(user_id_1: str, user_id_2: str) -> str:
    """
    Generate normalized conversation key (lower ID first)
    Example: get_conversation_key("9999", "1111") -> "1111_9999"
    """
    ids = sorted([str(user_id_1), str(user_id_2)])
    return f"{ids[0]}_{ids[1]}"

def get_conversation_history(user_id_1: str, user_id_2: str, max_messages: int = 10) -> List[Dict]:
    """
    Get conversation history between two users
    Returns last N messages (sorted oldest to newest)
    """
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            key = get_conversation_key(user_id_1, user_id_2)
            cur.execute("SELECT messages FROM conversations WHERE conversation_key = %s", (key,))
            row = cur.fetchone()
            
            if row:
                history = row[0]
                return history[-max_messages:] if history else []
            return []
    except Exception as e:
        print(f"Error getting conversation history: {e}")
        return []
    
def add_to_conversation(user_id_1: str, user_id_2: str, from_id: str, text: str, language: str, max_history: int = 10):
    """
    Add a message to conversation history
    Maintains sliding window of max_history messages
    """
    with get_db_cursor() as cur:
        key = get_conversation_key(user_id_1, user_id_2)
        
        # Get existing conversation
        cur.execute("SELECT messages FROM conversations WHERE conversation_key = %s", (key,))
        row = cur.fetchone()
        
        if row:
            messages = row[0]
        else:
            messages = []
        
        # Add new message
        message = {
            "from": str(from_id),
            "text": text,
            "lang": language,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        messages.append(message)
        
        # Keep only last max_history messages (sliding window)
        messages = messages[-max_history:]
        
        # Upsert conversation
        cur.execute("""
            INSERT INTO conversations (conversation_key, messages)
            VALUES (%s, %s)
            ON CONFLICT (conversation_key)
            DO UPDATE SET messages = EXCLUDED.messages
        """, (key, Json(messages)))
    # Auto-commits! ✅

def clear_conversation(user_id_1: str, user_id_2: str):
    """Clear conversation history between two users"""
    with get_db_cursor() as cur:
        key = get_conversation_key(user_id_1, user_id_2)
        cur.execute("DELETE FROM conversations WHERE conversation_key = %s", (key,))
    # Auto-commits! ✅

def format_history_for_prompt(history: List[Dict], current_user_id: str) -> str:
    """
    Format conversation history for translation prompt
    Returns a string like:
    - Manager: Check cow 115
    - Worker: She looks healthy
    """
    if not history:
        return ""
    
    formatted = "Recent conversation:\n"
    for msg in history:
        role = "You" if msg["from"] == current_user_id else "Other person"
        formatted += f"- {role}: {msg['text']}\n"
    
    return formatted

# Initialize database on import
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize conversations table: {e}")