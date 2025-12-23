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

def init_subscriptions_table():
    """Create subscriptions table if it doesn't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            telegram_user_id TEXT PRIMARY KEY,
            data JSONB NOT NULL
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def get_subscription(telegram_user_id: str) -> Optional[Dict]:
    """
    Get subscription data for a Telegram user
    Returns dict with status, lemon_subscription_id, renews_at, etc.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT data FROM subscriptions WHERE telegram_user_id = %s", (str(telegram_user_id),))
        row = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return row[0] if row else None
    except Exception as e:
        print(f"Error getting subscription for {telegram_user_id}: {e}")
        return None

def save_subscription(telegram_user_id: str, subscription_data: Dict):
    """Save or update subscription data for a Telegram user"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Upsert (insert or update)
    cur.execute("""
        INSERT INTO subscriptions (telegram_user_id, data)
        VALUES (%s, %s)
        ON CONFLICT (telegram_user_id)
        DO UPDATE SET data = EXCLUDED.data
    """, (str(telegram_user_id), Json(subscription_data)))
    
    conn.commit()
    cur.close()
    conn.close()

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
            if datetime.utcnow().replace(tzinfo=ends_at.tzinfo) < ends_at:
                return True
    
    return False

def create_checkout_url(telegram_user_id: str) -> str:
    """
    Generate Lemon Squeezy checkout URL with telegram_id as custom data
    """
    config = load_config()
    
    store_url = config['lemonsqueezy']['store_url']  # e.g., "bridgeos.lemonsqueezy.com"
    variant_id = config['lemonsqueezy']['variant_id']  # e.g., "1166995"
    
    checkout_url = f"https://{store_url}/checkout/buy/{variant_id}?checkout[custom][telegram_id]={telegram_user_id}"
    
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
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM subscriptions WHERE telegram_user_id = %s", (str(telegram_user_id),))
    
    conn.commit()
    cur.close()
    conn.close()

def get_all_subscriptions() -> Dict:
    """Get all subscriptions (for dashboard)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT telegram_user_id, data FROM subscriptions")
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        print(f"Error getting all subscriptions: {e}")
        return {}

# Initialize table on import
try:
    init_subscriptions_table()
except Exception as e:
    print(f"Warning: Could not initialize subscriptions table: {e}")