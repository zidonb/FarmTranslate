import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from typing import Optional, Dict
from config import load_config

def get_db_connection():
    """Get PostgreSQL connection from Railway DATABASE_URL"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL not found in environment variables")
    return psycopg2.connect(database_url)

def init_db():
    """Create usage_tracking table if it doesn't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create usage_tracking table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_tracking (
            telegram_user_id TEXT PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def get_usage(telegram_user_id: str) -> Dict:
    """
    Get usage data for a Telegram user
    Returns dict with messages_sent, blocked, first_seen, last_message
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT data FROM usage_tracking WHERE telegram_user_id = %s", (str(telegram_user_id),))
        row = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if row:
            return row[0]
        else:
            # Return default values for new user
            return {
                'messages_sent': 0,
                'blocked': False,
                'first_seen': datetime.utcnow().isoformat(),
                'last_message': None
            }
    except Exception as e:
        print(f"Error getting usage for {telegram_user_id}: {e}")
        return {'messages_sent': 0, 'blocked': False, 'first_seen': None, 'last_message': None}

def save_usage(telegram_user_id: str, usage_data: Dict):
    """Save or update usage data for a Telegram user"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Upsert (insert or update)
    cur.execute("""
        INSERT INTO usage_tracking (telegram_user_id, data)
        VALUES (%s, %s)
        ON CONFLICT (telegram_user_id)
        DO UPDATE SET data = EXCLUDED.data
    """, (str(telegram_user_id), Json(usage_data)))
    
    conn.commit()
    cur.close()
    conn.close()

def is_user_blocked(telegram_user_id: str) -> bool:
    """Check if user has reached message limit and is blocked"""
    usage = get_usage(telegram_user_id)
    return usage.get('blocked', False)

def increment_message_count(telegram_user_id: str) -> bool:
    """
    Increment message counter for user
    Returns True if message allowed, False if limit reached
    """
    config = load_config()
    free_limit = config.get('free_message_limit', 50)
    enforce_limits = config.get('enforce_limits', False)
    
    # If limits not enforced, always allow
    if not enforce_limits:
        return True
    
    # Get current usage
    usage = get_usage(telegram_user_id)
    
    # If already blocked, deny
    if usage.get('blocked', False):
        return False
    
    # Increment counter
    usage['messages_sent'] = usage.get('messages_sent', 0) + 1
    usage['last_message'] = datetime.utcnow().isoformat()
    
    # Check if limit reached
    if usage['messages_sent'] >= free_limit:
        usage['blocked'] = True
    
    # Save updated usage
    save_usage(telegram_user_id, usage)
    
    # Return whether user is now blocked
    return not usage['blocked']

def block_user(telegram_user_id: str):
    """Manually block a user from sending messages"""
    usage = get_usage(telegram_user_id)
    usage['blocked'] = True
    save_usage(telegram_user_id, usage)

def unblock_user(telegram_user_id: str):
    """Manually unblock a user (e.g., after payment)"""
    usage = get_usage(telegram_user_id)
    usage['blocked'] = False
    save_usage(telegram_user_id, usage)

def reset_user_usage(telegram_user_id: str):
    """Admin function: Reset usage counter for a user (keeps history)"""
    usage = get_usage(telegram_user_id)
    usage['messages_sent'] = 0
    usage['blocked'] = False
    save_usage(telegram_user_id, usage)

def get_all_usage() -> Dict:
    """Get usage data for all users (for dashboard)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT telegram_user_id, data FROM usage_tracking")
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        # Convert to dictionary
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error getting all usage: {e}")
        return {}

def get_usage_stats() -> Dict:
    """Get aggregated usage statistics"""
    all_usage = get_all_usage()
    
    total_users = len(all_usage)
    total_messages = sum(u.get('messages_sent', 0) for u in all_usage.values())
    blocked_users = sum(1 for u in all_usage.values() if u.get('blocked', False))
    active_users = total_users - blocked_users
    
    return {
        'total_users_tracked': total_users,
        'total_messages_sent': total_messages,
        'blocked_users': blocked_users,
        'active_users': active_users
    }

# Initialize database on import
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize usage_tracking table: {e}")