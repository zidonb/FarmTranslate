import os
import json
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from typing import List, Dict, Optional

def get_db_connection():
    """Get PostgreSQL connection from Railway DATABASE_URL"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL not found in environment variables")
    return psycopg2.connect(database_url)

def init_db():
    """Create conversations table if it doesn't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create conversations table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_key TEXT PRIMARY KEY,
            messages JSONB NOT NULL
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def load_conversations():
    """Load all conversations as a dictionary (compatible with old JSON approach)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT conversation_key, messages FROM conversations")
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        # Convert to dictionary format
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error loading conversations: {e}")
        return {}

def save_conversations(data):
    """Save all conversations (bulk update)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Clear existing data
    cur.execute("DELETE FROM conversations")
    
    # Insert all conversations
    for conv_key, messages in data.items():
        cur.execute(
            "INSERT INTO conversations (conversation_key, messages) VALUES (%s, %s)",
            (conv_key, Json(messages))
        )
    
    conn.commit()
    cur.close()
    conn.close()

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
        conn = get_db_connection()
        cur = conn.cursor()
        
        key = get_conversation_key(user_id_1, user_id_2)
        cur.execute("SELECT messages FROM conversations WHERE conversation_key = %s", (key,))
        row = cur.fetchone()
        
        cur.close()
        conn.close()
        
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
    conn = get_db_connection()
    cur = conn.cursor()
    
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
        "timestamp": datetime.utcnow().isoformat()
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
    
    conn.commit()
    cur.close()
    conn.close()

def clear_conversation(user_id_1: str, user_id_2: str):
    """Clear conversation history between two users"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    key = get_conversation_key(user_id_1, user_id_2)
    cur.execute("DELETE FROM conversations WHERE conversation_key = %s", (key,))
    
    conn.commit()
    cur.close()
    conn.close()

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