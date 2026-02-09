"""
Subscription model — manager billing via LemonSqueezy.
"""
import logging
from typing import Optional, Dict
from datetime import datetime, timezone
from config import load_config
from utils.db_connection import get_db_cursor

logger = logging.getLogger(__name__)


def get_by_manager(manager_id: int) -> Optional[Dict]:
    """Get subscription for a manager."""
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT subscription_id, manager_id, external_id, status,
                   customer_portal_url, renews_at, ends_at, created_at
            FROM subscriptions WHERE manager_id = %s
        """, (manager_id,))
        row = cur.fetchone()

    if not row:
        return None

    return {
        'subscription_id': row[0],
        'manager_id': row[1],
        'external_id': row[2],
        'status': row[3],
        'customer_portal_url': row[4],
        'renews_at': row[5],
        'ends_at': row[6],
        'created_at': row[7],
    }


def is_active(manager_id: int) -> bool:
    """
    Check if manager has active access.
    Returns True if subscription is active, or cancelled but not yet expired.
    """
    sub = get_by_manager(manager_id)
    if not sub:
        return False

    status = sub.get('status')

    if status == 'active':
        return True

    # Cancelled but still has access until end date
    if status == 'cancelled':
        ends_at = sub.get('ends_at')
        if ends_at and datetime.now(timezone.utc) < ends_at:
            return True

    return False


def save(manager_id: int, external_id: str = None, status: str = 'active',
         customer_portal_url: str = None, renews_at=None, ends_at=None):
    """Create or update subscription."""
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO subscriptions (manager_id, external_id, status,
                                       customer_portal_url, renews_at, ends_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (manager_id) DO UPDATE SET
                external_id = EXCLUDED.external_id,
                status = EXCLUDED.status,
                customer_portal_url = EXCLUDED.customer_portal_url,
                renews_at = EXCLUDED.renews_at,
                ends_at = EXCLUDED.ends_at,
                updated_at = NOW()
        """, (manager_id, external_id, status, customer_portal_url, renews_at, ends_at))

    logger.info(f"Subscription saved: manager={manager_id}, status={status}")


def update_status(manager_id: int, status: str, ends_at=None):
    """Update subscription status (e.g. after webhook callback)."""
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE subscriptions
            SET status = %s, ends_at = %s, updated_at = NOW()
            WHERE manager_id = %s
        """, (status, ends_at, manager_id))

    logger.info(f"Subscription status updated: manager={manager_id}, status={status}")


def create_checkout_url(manager_id: int) -> str:
    """Generate LemonSqueezy checkout URL with telegram_id as custom data."""
    config = load_config()
    store_url = config['lemonsqueezy']['store_url']
    checkout_id = config['lemonsqueezy']['checkout_id']
    return (
        f"https://{store_url}/checkout/buy/{checkout_id}"
        f"?checkout[custom][telegram_id]={manager_id}"
    )


def delete(manager_id: int):
    """Delete subscription record."""
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM subscriptions WHERE manager_id = %s", (manager_id,))

    logger.info(f"Subscription deleted: manager={manager_id}")


def get_all() -> list:
    """Get all subscriptions (for dashboard)."""
    with get_db_cursor(commit=False) as cur:
        cur.execute("""
            SELECT s.subscription_id, s.manager_id, s.status, s.renews_at, s.ends_at,
                   u.telegram_name
            FROM subscriptions s
            JOIN users u ON s.manager_id = u.user_id
            ORDER BY s.created_at DESC
        """)
        rows = cur.fetchall()

    return [
        {
            'subscription_id': r[0],
            'manager_id': r[1],
            'status': r[2],
            'renews_at': r[3],
            'ends_at': r[4],
            'telegram_name': r[5],
        }
        for r in rows
    ]
