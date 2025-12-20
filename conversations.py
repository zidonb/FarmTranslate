import json
import os
from datetime import datetime
from typing import List, Dict, Optional

CONVERSATIONS_FILE = "conversations.json"

def load_conversations():
    """Load all conversations from file"""
    if not os.path.exists(CONVERSATIONS_FILE):
        return {}
    with open(CONVERSATIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_conversations(data):
    """Save all conversations to file"""
    with open(CONVERSATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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
    conversations = load_conversations()
    key = get_conversation_key(user_id_1, user_id_2)
    history = conversations.get(key, [])
    
    # Return last max_messages
    return history[-max_messages:] if history else []

def add_to_conversation(user_id_1: str, user_id_2: str, from_id: str, text: str, language: str, max_history: int = 10):
    """
    Add a message to conversation history
    Maintains sliding window of max_history messages
    """
    conversations = load_conversations()
    key = get_conversation_key(user_id_1, user_id_2)
    
    # Get or create conversation
    if key not in conversations:
        conversations[key] = []
    
    # Add new message
    message = {
        "from": str(from_id),
        "text": text,
        "lang": language,
        "timestamp": datetime.utcnow().isoformat()
    }
    conversations[key].append(message)
    
    # Keep only last max_history messages (sliding window)
    conversations[key] = conversations[key][-max_history:]
    
    # Save
    save_conversations(conversations)

def clear_conversation(user_id_1: str, user_id_2: str):
    """Clear conversation history between two users"""
    conversations = load_conversations()
    key = get_conversation_key(user_id_1, user_id_2)
    
    if key in conversations:
        del conversations[key]
        save_conversations(conversations)

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