import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone
from typing import Optional, Dict
from config import load_config
from db_connection import get_db_cursor


def init_db():
    """Create usage_tracking table if it doesn't exist"""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usage_tracking (
                telegram_user_id TEXT PRIMARY KEY,
                data JSONB NOT NULL
            )
        """)
    # Auto-commits! ✅

def get_usage(telegram_user_id: str) -> Dict:
    """
    Get usage data for a Telegram user
    Returns dict with messages_sent, blocked, first_seen, last_message
    """
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only, no commit needed
            cur.execute("SELECT data FROM usage_tracking WHERE telegram_user_id = %s", (str(telegram_user_id),))
            row = cur.fetchone()
        
        if row:
            return row[0]
        else:
            # Return default values for new user
            return {
                'messages_sent': 0,
                'blocked': False,
                'first_seen': datetime.now(timezone.utc).isoformat(),
                'last_message': None
            }
    except Exception as e:
        print(f"Error getting usage for {telegram_user_id}: {e}")
        return {'messages_sent': 0, 'blocked': False, 'first_seen': None, 'last_message': None}

def save_usage(telegram_user_id: str, usage_data: Dict):
    """Save or update usage data for a Telegram user"""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO usage_tracking (telegram_user_id, data)
            VALUES (%s, %s)
            ON CONFLICT (telegram_user_id)
            DO UPDATE SET data = EXCLUDED.data
        """, (str(telegram_user_id), Json(usage_data)))
    # Auto-commits! ✅

def is_user_blocked(telegram_user_id: str) -> bool:
    """Check if user has reached message limit and is blocked"""
    # Check whitelist first
    config = load_config()
    
    # If testing mode is on, check whitelist
    if config.get('testing_mode', False):
        test_user_ids = config.get('test_user_ids', [])
        if str(telegram_user_id) in test_user_ids:
            return False  # Whitelisted users never blocked
    
    usage = get_usage(telegram_user_id)
    return usage.get('blocked', False)

def increment_message_count(telegram_user_id: str) -> bool:
    """
    Atomically increment message counter for user
    Returns True if message allowed, False if limit reached
    """
    config = load_config()
    free_limit = config.get('free_message_limit', 50)
    enforce_limits = config.get('enforce_limits', False)
    
    # If limits not enforced, always allow
    if not enforce_limits:
        return True
    
    # ✅ FIX: Atomic increment with race condition protection
    with get_db_cursor() as cur:
        # First, ensure row exists (upsert if needed)
        cur.execute("""
            INSERT INTO usage_tracking (telegram_user_id, data)
            VALUES (%s, %s)
            ON CONFLICT (telegram_user_id) DO NOTHING
        """, (str(telegram_user_id), Json({
            'messages_sent': 0,
            'blocked': False,
            'first_seen': datetime.now(timezone.utc).isoformat(),
            'last_message': None
        })))
        
        # ✅ Atomic increment + check limit in single operation
        cur.execute("""
            UPDATE usage_tracking
            SET data = jsonb_set(
                jsonb_set(
                    data,
                    '{messages_sent}',
                    to_jsonb((COALESCE((data->>'messages_sent')::int, 0) + 1))
                ),
                '{last_message}',
                to_jsonb(%s::text)
            )
            WHERE telegram_user_id = %s
            RETURNING 
                (data->>'messages_sent')::int as messages_sent,
                (data->>'blocked')::boolean as blocked
        """, (datetime.now(timezone.utc).isoformat(), str(telegram_user_id)))
        
        result = cur.fetchone()
        
        if not result:
            # This shouldn't happen due to INSERT above, but handle gracefully
            return True
        
        messages_sent, currently_blocked = result
        
        # If already blocked, deny
        if currently_blocked:
            return False
        
        # Check if just hit the limit
        if messages_sent >= free_limit:
            # ✅ Atomically block user
            cur.execute("""
                UPDATE usage_tracking
                SET data = jsonb_set(data, '{blocked}', 'true'::jsonb)
                WHERE telegram_user_id = %s
            """, (str(telegram_user_id),))
            return False  # This message NOT allowed (just hit limit)
        
        return True  # Message allowed
    # Auto-commits all changes atomically

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
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT telegram_user_id, data FROM usage_tracking")
            rows = cur.fetchall()
            
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