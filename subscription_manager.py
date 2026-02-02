import os
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from typing import Optional, Dict
from config import load_config
from db_connection import get_db_cursor
from datetime import datetime, timezone


def init_subscriptions_table():
    """Create subscriptions table if it doesn't exist"""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                telegram_user_id TEXT PRIMARY KEY,
                data JSONB NOT NULL
            )
        """)
    # Auto-commits! ✅

def get_subscription(telegram_user_id: str) -> Optional[Dict]:
    """
    Get subscription data for a Telegram user
    Returns dict with status, lemon_subscription_id, renews_at, etc.
    """
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT data FROM subscriptions WHERE telegram_user_id = %s", (str(telegram_user_id),))
            row = cur.fetchone()
            
            return row[0] if row else None
    except Exception as e:
        print(f"Error getting subscription for {telegram_user_id}: {e}")
        return None

def save_subscription(telegram_user_id: str, subscription_data: Dict):
    """Save or update subscription data for a Telegram user"""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO subscriptions (telegram_user_id, data)
            VALUES (%s, %s)
            ON CONFLICT (telegram_user_id)
            DO UPDATE SET data = EXCLUDED.data
        """, (str(telegram_user_id), Json(subscription_data)))
    # Auto-commits! ✅

def is_subscribed(telegram_user_id: str) -> bool:
    """
    Check if user has active access (active subscription or cancelled but not expired)
    Returns True if user can send unlimited messages
    """
    subscription = get_subscription(telegram_user_id)
    
    if not subscription:
        return False
    
    status = subscription.get('status')
    
    # Active subscription
    if status == 'active':
        return True
    
    # Cancelled but still has access until end date
    if status == 'cancelled':
        ends_at_str = subscription.get('ends_at')
        if ends_at_str:
            ends_at = datetime.fromisoformat(ends_at_str.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) < ends_at:
                return True
    
    return False

def create_checkout_url(telegram_user_id: str) -> str:
    """
    Generate Lemon Squeezy checkout URL with telegram_id as custom data
    """
    config = load_config()
    
    store_url = config['lemonsqueezy']['store_url']  # e.g., "bridgeos.lemonsqueezy.com"
    checkout_id = config['lemonsqueezy']['checkout_id']
    
    checkout_url = f"https://{store_url}/checkout/buy/{checkout_id}?checkout[custom][telegram_id]={telegram_user_id}"
    return checkout_url

def get_customer_portal_url(telegram_user_id: str) -> Optional[str]:
    """
    Get customer portal URL from subscription data
    User can manage/cancel subscription here
    """
    subscription = get_subscription(telegram_user_id)
    
    if not subscription:
        return None
    
    return subscription.get('customer_portal_url')

def delete_subscription(telegram_user_id: str):
    """Delete subscription data (for testing or admin actions)"""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM subscriptions WHERE telegram_user_id = %s", (str(telegram_user_id),))
    # Auto-commits! ✅

def get_all_subscriptions() -> Dict:
    """Get all subscriptions (for dashboard)"""
    try:
        with get_db_cursor(commit=False) as cur:  # ✅ Read-only
            cur.execute("SELECT telegram_user_id, data FROM subscriptions")
            rows = cur.fetchall()
            
            return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error getting all subscriptions: {e}")
        return {}

# Initialize table on import
try:
    init_subscriptions_table()
except Exception as e:
    print(f"Warning: Could not initialize subscriptions table: {e}")