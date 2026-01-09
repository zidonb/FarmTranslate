from flask import Flask, render_template_string, request, redirect, session, jsonify
import database
import translation_msg_context
import message_history
import usage_tracker
import subscription_manager
import feedback
from config import load_config
from datetime import datetime
import secrets
import hmac
import hashlib
import requests
import db_connection

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Simple password protection
DASHBOARD_PASSWORD = "zb280072A"  # Change this!

# ============================================
# LEMON SQUEEZY WEBHOOK HANDLER
# ============================================


def verify_signature(payload_body, signature_header, secret):
    """Verify Lemon Squeezy webhook signature"""
    computed_signature = hmac.new(
        secret.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed_signature, signature_header)


def send_telegram_notification(chat_id, text):
    """Send Telegram message directly via Bot API"""
    try:
        config = load_config()
        token = config["telegram_token"]

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        response = requests.post(
            url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )

        if response.status_code == 200:
            print(f"✅ Notification sent to {chat_id}")
        else:
            print(f"⚠️ Failed to send notification: {response.text}")
    except Exception as e:
        print(f"❌ Error sending notification: {e}")


@app.route("/webhook/lemonsqueezy", methods=["POST"])
def lemonsqueezy_webhook():
    """Handle Lemon Squeezy webhook events"""
    try:
        config = load_config()
        webhook_secret = config["lemonsqueezy"]["webhook_secret"]

        payload_body = request.get_data()
        signature_header = request.headers.get("X-Signature")

        if not signature_header:
            print("ERROR: No signature header")
            return jsonify({"error": "No signature"}), 401

        if not verify_signature(payload_body, signature_header, webhook_secret):
            print("ERROR: Invalid signature")
            return jsonify({"error": "Invalid signature"}), 401

        data = request.json
        event_name = data["meta"]["event_name"]
        custom_data = data["meta"].get("custom_data", {})
        telegram_id = custom_data.get("telegram_id")

        if not telegram_id:
            print(f"WARNING: No telegram_id in webhook for event {event_name}")
            return jsonify({"status": "success", "note": "no telegram_id"}), 200

        print(f"Processing event: {event_name} for telegram_id: {telegram_id}")

        # Handle different event types
        if event_name == "subscription_created":
            handle_subscription_created(telegram_id, data)
        elif event_name == "subscription_updated":
            handle_subscription_updated(telegram_id, data)
        elif event_name == "subscription_cancelled":
            handle_subscription_cancelled(telegram_id, data)
        elif event_name == "subscription_resumed":
            handle_subscription_resumed(telegram_id, data)
        elif event_name == "subscription_expired":
            handle_subscription_expired(telegram_id, data)
        elif event_name == "subscription_paused":
            handle_subscription_paused(telegram_id, data)
        elif event_name == "subscription_unpaused":
            handle_subscription_unpaused(telegram_id, data)
        elif event_name == "subscription_payment_success":
            handle_subscription_payment_success(telegram_id, data)
        elif event_name == "subscription_payment_failed":
            handle_subscription_payment_failed(telegram_id, data)
        elif event_name == "subscription_payment_recovered":
            handle_subscription_payment_recovered(telegram_id, data)
        else:
            print(f"Unhandled event: {event_name}")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"ERROR processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200


def handle_subscription_created(telegram_id: str, data: dict):
    """Handle subscription_created event"""
    attrs = data["data"]["attributes"]
    subscription_data = {
        "status": "active",
        "lemon_subscription_id": data["data"]["id"],
        "lemon_customer_id": str(attrs["customer_id"]),
        "started_at": attrs["created_at"],
        "renews_at": attrs["renews_at"],
        "ends_at": attrs.get("ends_at"),
        "cancelled_at": None,
        "plan": "monthly",
        "customer_portal_url": attrs["urls"]["customer_portal"],
    }
    subscription_manager.save_subscription(telegram_id, subscription_data)
    print(
        f"✅ Subscription created for {telegram_id}: {subscription_data['lemon_subscription_id']}"
    )

    # Unblock user and reset usage counter
    usage_tracker.unblock_user(telegram_id)
    usage_tracker.reset_user_usage(telegram_id)
    print(f"✅ User {telegram_id} unblocked and usage reset")

    # Send notification to user
    send_telegram_notification(
        telegram_id,
        "✅ *Subscription Active!*\n\n"
        "You now have unlimited messages.\n"
        "Thank you for subscribing to BridgeOS! 🎉",
    )


def handle_subscription_updated(telegram_id: str, data: dict):
    """Handle subscription_updated event"""
    attrs = data["data"]["attributes"]
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}, creating new")
        handle_subscription_created(telegram_id, data)
        return
    subscription["renews_at"] = attrs["renews_at"]
    subscription["ends_at"] = attrs.get("ends_at")
    subscription["customer_portal_url"] = attrs["urls"]["customer_portal"]
    if attrs["cancelled"]:
        subscription["status"] = "cancelled"
        if not subscription.get("cancelled_at"):
            subscription["cancelled_at"] = datetime.utcnow().isoformat()
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"✅ Subscription updated for {telegram_id}")


def handle_subscription_cancelled(telegram_id: str, data: dict):
    """Handle subscription_cancelled event"""
    attrs = data["data"]["attributes"]
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    subscription["status"] = "cancelled"
    subscription["cancelled_at"] = datetime.utcnow().isoformat()
    subscription["ends_at"] = attrs.get("ends_at")
    subscription_manager.save_subscription(telegram_id, subscription)
    print(
        f"⚠️ Subscription cancelled for {telegram_id}, access until: {attrs.get('ends_at')}"
    )

    # Send notification to user
    ends_at_display = (
        attrs.get("ends_at", "end of billing period")[:10]
        if attrs.get("ends_at")
        else "end of billing period"
    )
    send_telegram_notification(
        telegram_id,
        f"⚠️ *Subscription Cancelled*\n\n"
        f"You'll keep access until {ends_at_display}.\n"
        f"You can resubscribe anytime.",
    )


def handle_subscription_resumed(telegram_id: str, data: dict):
    """Handle subscription_resumed event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    subscription["status"] = "active"
    subscription["cancelled_at"] = None
    subscription["ends_at"] = None
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"✅ Subscription resumed for {telegram_id}")
    # Unblock user
    usage_tracker.unblock_user(telegram_id)
    print(f"✅ User {telegram_id} unblocked")

    # Send notification to user
    send_telegram_notification(
        telegram_id,
        "✅ *Subscription Resumed!*\n\n"
        "Your subscription is active again.\n"
        "Welcome back! 🎉",
    )


def handle_subscription_expired(telegram_id: str, data: dict):
    """Handle subscription_expired event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    subscription["status"] = "expired"
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"❌ Subscription expired for {telegram_id}")

    # Block user if they previously hit the free limit
    usage = usage_tracker.get_usage(telegram_id)
    config = load_config()
    free_limit = config.get('free_message_limit', 50)

    if usage.get('messages_sent', 0) >= free_limit:
        usage_tracker.block_user(telegram_id)
        print(f"🚫 User {telegram_id} blocked (exceeded free limit)")

    # Send notification to user
    send_telegram_notification(
        telegram_id,
        "❌ *Subscription Expired*\n\n"
        "Your subscription has ended.\n"
        "You're back on the free tier (50 messages).\n\n"
        "Subscribe again to continue unlimited messaging.",
    )


def handle_subscription_paused(telegram_id: str, data: dict):
    """Handle subscription_paused event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    subscription["status"] = "paused"
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"â¸ï¸ Subscription paused for {telegram_id}")


def handle_subscription_unpaused(telegram_id: str, data: dict):
    """Handle subscription_unpaused event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    subscription["status"] = "active"
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"â–¶ï¸ Subscription unpaused for {telegram_id}")


def handle_subscription_payment_success(telegram_id: str, data: dict):
    """Handle subscription_payment_success event"""
    print(f"✅ Payment successful for {telegram_id}")


def handle_subscription_payment_failed(telegram_id: str, data: dict):
    """Handle subscription_payment_failed event"""
    print(f"⚠️ Payment failed for {telegram_id}")

    # Send notification to user
    subscription = subscription_manager.get_subscription(telegram_id)
    portal_url = subscription.get("customer_portal_url") if subscription else None

    message = (
        "⚠️ *Payment Failed*\n\n"
        "Your last payment didn't go through.\n"
        "We'll retry automatically in 3 days.\n\n"
    )

    if portal_url:
        message += f"Update your payment method: {portal_url}"

    send_telegram_notification(telegram_id, message)


def handle_subscription_payment_recovered(telegram_id: str, data: dict):
    """Handle subscription_payment_recovered event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if subscription and subscription["status"] == "paused":
        subscription["status"] = "active"
        subscription_manager.save_subscription(telegram_id, subscription)
    print(f"✅ Payment recovered for {telegram_id}")
    # Unblock user
    usage_tracker.unblock_user(telegram_id)
    print(f"✅ User {telegram_id} unblocked")


# ============================================
# DASHBOARD (Original Code)
# ============================================

# HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BridgeOS Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="30">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            position: relative;
        }
        .header h1 { font-size: 32px; margin-bottom: 10px; }
        .header p { opacity: 0.9; font-size: 14px; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            font-size: 14px;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .stat-card .number {
            font-size: 36px;
            font-weight: bold;
            color: #667eea;
        }
        .section {
            background: white;
            padding: 25px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .section h2 {
            font-size: 20px;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .user-card {
            background: #f9f9f9;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .user-card.worker { border-left-color: #48bb78; }
        .user-card h3 {
            font-size: 16px;
            margin-bottom: 10px;
            color: #333;
        }
        .user-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
            font-size: 14px;
            color: #666;
        }
        .user-info div { padding: 5px 0; }
        .user-info strong { color: #333; display: inline-block; min-width: 100px; }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .badge.connected { background: #48bb78; color: white; }
        .badge.disconnected { background: #f56565; color: white; }
        .badge.subscribed { background: #4299e1; color: white; }
        .conversation {
            background: #f9f9f9;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 8px;
        }
        .conversation h3 {
            font-size: 14px;
            margin-bottom: 10px;
            color: #667eea;
        }
        .message {
            padding: 8px;
            margin: 5px 0;
            font-size: 13px;
            border-left: 3px solid #ddd;
            padding-left: 12px;
        }
        .message.from-manager { border-left-color: #667eea; }
        .message.from-worker { border-left-color: #48bb78; }
        .message-time {
            font-size: 11px;
            color: #999;
            margin-right: 8px;
        }
        .btn {
            display: inline-block;
            padding: 8px 16px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-size: 14px;
            border: none;
            cursor: pointer;
            margin-right: 5px;
        }
        .btn:hover { background: #5568d3; }
        .btn.danger { background: #f56565; }
        .btn.danger:hover { background: #e53e3e; }
        .actions { margin-top: 10px; }
        .logout {
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(255,255,255,0.2);
            color: white;
            padding: 8px 16px;
            border-radius: 5px;
            text-decoration: none;
            font-size: 14px;
        }
        .logout:hover { background: rgba(255,255,255,0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a href="/logout" class="logout">🚪 Logout</a>
            <h1>🌉 BridgeOS Dashboard</h1>
            <p>Real-time monitoring • Auto-refresh every 30 seconds • Last updated: {{ now }}</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <h3>Total Managers</h3>
                <div class="number">{{ stats.total_managers }}</div>
            </div>
            <div class="stat-card">
                <h3>Total Workers</h3>
                <div class="number">{{ stats.total_workers }}</div>
            </div>
            <div class="stat-card">
                <h3>Active Connections</h3>
                <div class="number">{{ stats.active_connections }}</div>
            </div>
            <div class="stat-card">
                <h3>Total Messages</h3>
                <div class="number">{{ stats.total_messages }}</div>
            </div>
            <div class="stat-card">
                <h3>Subscriptions</h3>
                <div class="number">{{ stats.total_subscriptions }}</div>
            </div>
        </div>

        <div class="section">
            <h2>👔 Managers</h2>
            {% if managers %}
                {% for manager in managers %}
                <div class="user-card">
                    <h3>Manager ID: {{ manager.id }}</h3>
                    <div class="user-info">
                        <div><strong>Code:</strong> {{ manager.code }}</div>
                        <div><strong>Language:</strong> {{ manager.language }}</div>
                        <div><strong>Gender:</strong> {{ manager.gender }}</div>
                        <div><strong>Industry:</strong> {{ manager.industry }}</div>
                        <div><strong>Messages Sent:</strong> {{ manager.messages_sent }} / {{ manager.message_limit }}</div>
                        <div>
                            <strong>Status:</strong>
                            {% if manager.blocked %}
                                <span class="badge disconnected">🚫 Blocked</span>
                            {% else %}
                                <span class="badge connected">✔ Active</span>
                            {% endif %}
                        </div>
                        <div>
                            <strong>Subscription:</strong>
                            {% if manager.subscription %}
                                <span class="badge subscribed">💳 {{ manager.subscription.status|title }}</span>
                            {% else %}
                                <span class="badge disconnected">Free Tier</span>
                            {% endif %}
                        </div>
                        <div>
                            <strong>Worker:</strong> 
                            {% if manager.worker %}
                                <span class="badge connected">✔ Connected ({{ manager.worker }})</span>
                            {% else %}
                                <span class="badge disconnected">✗ No Worker</span>
                            {% endif %}
                        </div>
                    </div>
                    <div class="actions">
                        <a href="/manager/{{ manager.id }}" class="btn">👁️ View Details</a>
                        <form method="POST" action="/delete_user/{{ manager.id }}" style="display:inline;" 
                              onsubmit="return confirm('Delete this manager and all their data?');">
                            <button type="submit" class="btn danger">🗑️ Delete Manager</button>
                        </form>
                        {% if manager.blocked %}
                        <form method="POST" action="/reset_usage/{{ manager.id }}" style="display:inline;">
                            <button type="submit" class="btn">🔄 Reset Usage</button>
                        </form>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No managers registered yet.</p>
            {% endif %}
        </div>

        <div class="section">
            <h2>👷Workers</h2>
            {% if workers %}
                {% for worker in workers %}
                <div class="user-card worker">
                    <h3>Worker ID: {{ worker.id }}</h3>
                    <div class="user-info">
                        <div><strong>Language:</strong> {{ worker.language }}</div>
                        <div><strong>Gender:</strong> {{ worker.gender }}</div>
                        <div><strong>Manager:</strong> {{ worker.manager }}</div>
                    </div>
                    <div class="actions">
                        <form method="POST" action="/delete_user/{{ worker.id }}" style="display:inline;"
                              onsubmit="return confirm('Delete this worker?');">
                            <button type="submit" class="btn danger">🗑️ Delete Worker</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No workers registered yet.</p>
            {% endif %}
        </div>

        <div class="section">
            <h2>💳 Subscriptions</h2>
            {% if subscriptions_list %}
                {% for sub in subscriptions_list %}
                <div class="user-card">
                    <h3>Telegram ID: {{ sub.telegram_id }}</h3>
                    <div class="user-info">
                        <div><strong>Status:</strong> 
                            {% if sub.status == 'active' %}
                                <span class="badge subscribed">✔ Active</span>
                            {% elif sub.status == 'cancelled' %}
                                <span class="badge disconnected">⚠️ Cancelled</span>
                            {% elif sub.status == 'expired' %}
                                <span class="badge disconnected">❌ Expired</span>
                            {% elif sub.status == 'paused' %}
                                <span class="badge disconnected">â¸ï¸ Paused</span>
                            {% endif %}
                        </div>
                        <div><strong>Plan:</strong> {{ sub.plan|title }}</div>
                        <div><strong>Started:</strong> {{ sub.started_at[:10] }}</div>
                        <div><strong>Renews:</strong> {{ sub.renews_at[:10] if sub.renews_at else 'N/A' }}</div>
                        {% if sub.ends_at %}
                        <div><strong>Ends:</strong> {{ sub.ends_at[:10] }}</div>
                        {% endif %}
                        {% if sub.cancelled_at %}
                        <div><strong>Cancelled:</strong> {{ sub.cancelled_at[:10] }}</div>
                        {% endif %}
                        <div><strong>Lemon ID:</strong> {{ sub.lemon_subscription_id }}</div>
                    </div>
                    <div class="actions">
                        {% if sub.customer_portal_url %}
                        <a href="{{ sub.customer_portal_url }}" target="_blank" class="btn">🔗 Customer Portal</a>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No subscriptions yet.</p>
            {% endif %}
        </div>

        <div class="section">
            <h2>💬 Recent Conversations</h2>
            {% if conversations_list %}
                {% for conv in conversations_list %}
                <div class="conversation">
                    <h3>{{ conv.user1 }} ↔ {{ conv.user2 }}</h3>
                    {% for msg in conv.messages %}
                    <div class="message {{ 'from-manager' if msg.is_manager else 'from-worker' }}">
                        <span class="message-time">{{ msg.time }}</span>
                        <strong>{{ msg.from_role }}:</strong> {{ msg.text }} <em>({{ msg.lang }})</em>
                    </div>
                    {% endfor %}
                    <div class="actions">
                        <form method="POST" action="/clear_conversation/{{ conv.key }}" style="display:inline;"
                              onsubmit="return confirm('Clear this conversation history?');">
                            <button type="submit" class="btn danger">🧹 Clear History</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No conversations yet.</p>
            {% endif %}
        </div>
        <div class="section">
            <h2>💬 User Feedback</h2>
            {% if feedback_list %}
                {% for fb in feedback_list %}
                <div class="user-card">
                    <h3>{{ fb.user_name }}{% if fb.username %} (@{{ fb.username }}){% endif %}</h3>
                    <div class="user-info">
                        <div><strong>User ID:</strong> {{ fb.telegram_user_id }}</div>
                        <div><strong>Date:</strong> {{ fb.created_at.strftime('%Y-%m-%d %H:%M') if fb.created_at else 'N/A' }}</div>
                        <div>
                            <strong>Status:</strong>
                            {% if fb.status == 'read' %}
                                <span class="badge connected">✅ Read</span>
                            {% else %}
                                <span class="badge disconnected">⭕ Unread</span>
                            {% endif %}
                        </div>
                    </div>
                    <div style="background: #f9f9f9; padding: 15px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #667eea;">
                        <strong>Message:</strong><br>
                        {{ fb.message }}
                    </div>
                    <div class="actions">
                        {% if fb.status == 'unread' %}
                        <form method="POST" action="/mark_feedback_read/{{ fb.id }}" style="display:inline;">
                            <button type="submit" class="btn">✅ Mark as Read</button>
                        </form>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No feedback received yet.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BridgeOS Dashboard - Login</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 400px;
        }
        .login-box h1 {
            font-size: 28px;
            margin-bottom: 10px;
            color: #333;
        }
        .login-box p {
            color: #666;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
        }
        .btn:hover { background: #5568d3; }
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 5px;
            margin-bottom: 20px;
            border-left: 4px solid #c33;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🌉 BridgeOS</h1>
        <p>Dashboard Login</p>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" placeholder="Enter dashboard password" required autofocus>
            </div>
            <button type="submit" class="btn">Login</button>
        </form>
    </div>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == DASHBOARD_PASSWORD:
            session["authenticated"] = True
            return redirect("/")
        else:
            return render_template_string(LOGIN_HTML, error="Invalid password")
    return render_template_string(LOGIN_HTML)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/")
def dashboard():
    if not session.get("authenticated"):
        return redirect("/login")

    all_users = database.get_all_users()
    config = load_config()
    message_limit = config.get("free_message_limit", 50)

    managers = []
    workers = []

    for user_id, user_data in all_users.items():
        user_data["id"] = user_id
        if user_data.get("role") == "manager":
            usage = usage_tracker.get_usage(user_id)
            user_data["messages_sent"] = usage.get("messages_sent", 0)

            # Get subscription status
            subscription = subscription_manager.get_subscription(user_id)
            user_data["subscription"] = subscription

            # Only show blocked if NOT subscribed
            if subscription and subscription.get('status') in ['active', 'cancelled']:
                user_data["blocked"] = False  # Subscribed = never blocked
            else:
                user_data["blocked"] = usage.get("blocked", False)  # Check usage tracker

            user_data["message_limit"] = message_limit

            managers.append(user_data)
        elif user_data.get("role") == "worker":
            workers.append(user_data)

    all_conversations = translation_msg_context.load_conversations()
    conversations_list = []

    for conv_key, messages in all_conversations.items():
        user1, user2 = conv_key.split("_")
        user1_data = database.get_user(user1)
        user2_data = database.get_user(user2)

        formatted_messages = []
        for msg in messages[-10:]:
            msg_time = datetime.fromisoformat(msg["timestamp"]).strftime("%H:%M")
            is_manager = False
            from_role = "User"
            if (
                user1_data
                and user1_data.get("role") == "manager"
                and msg["from"] == user1
            ):
                is_manager = True
                from_role = "Manager"
            elif (
                user2_data
                and user2_data.get("role") == "manager"
                and msg["from"] == user2
            ):
                is_manager = True
                from_role = "Manager"
            else:
                from_role = "Worker"

            formatted_messages.append(
                {
                    "time": msg_time,
                    "text": msg["text"],
                    "lang": msg["lang"],
                    "is_manager": is_manager,
                    "from_role": from_role,
                }
            )

        conversations_list.append(
            {
                "key": conv_key,
                "user1": user1,
                "user2": user2,
                "messages": formatted_messages,
            }
        )

    # Get subscription stats
    all_subscriptions = subscription_manager.get_all_subscriptions()
    active_subscriptions = sum(
        1
        for s in all_subscriptions.values()
        if s.get("status") in ["active", "cancelled"]
    )

    # Format subscriptions for display
    subscriptions_list = []
    for telegram_id, sub_data in all_subscriptions.items():
        sub_data["telegram_id"] = telegram_id
        subscriptions_list.append(sub_data)

    # Get feedback
    feedback_list = feedback.get_all_feedback(limit=50)

    stats = {
        "total_managers": len(managers),
        "total_workers": len(workers),
        "active_connections": sum(1 for m in managers if m.get("worker")),
        "total_messages": sum(len(msgs) for msgs in all_conversations.values()),
        "total_subscriptions": active_subscriptions,
    }

    return render_template_string(
        DASHBOARD_HTML,
        managers=managers,
        workers=workers,
        conversations_list=conversations_list,
        subscriptions_list=subscriptions_list,
        feedback_list=feedback_list,  # ← ADD THIS LINE
        stats=stats,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/delete_user/<user_id>", methods=["POST"])
def delete_user(user_id):
    if not session.get("authenticated"):
        return redirect("/login")

    user = database.get_user(user_id)
    if not user:
        return redirect("/")

    if user.get("role") == "manager":
        worker_id = user.get("worker")
        if worker_id:
            translation_msg_context.clear_conversation(user_id, worker_id)
            all_users = database.get_all_users()
            if worker_id in all_users:
                del all_users[worker_id]
                database.save_data(all_users)

    elif user.get("role") == "worker":
        manager_id = user.get("manager")
        if manager_id:
            manager = database.get_user(manager_id)
            if manager:
                manager["worker"] = None
                database.save_user(manager_id, manager)
            translation_msg_context.clear_conversation(user_id, manager_id)

    all_users = database.get_all_users()
    if user_id in all_users:
        del all_users[user_id]
        database.save_data(all_users)

    return redirect("/")


@app.route("/clear_conversation/<conv_key>", methods=["POST"])
def clear_conversation_route(conv_key):
    if not session.get("authenticated"):
        return redirect("/login")

    user1, user2 = conv_key.split("_")
    translation_msg_context.clear_conversation(user1, user2)

    return redirect("/")


@app.route("/reset_usage/<user_id>", methods=["POST"])
def reset_usage_route(user_id):
    if not session.get("authenticated"):
        return redirect("/login")

    usage_tracker.reset_user_usage(user_id)

    return redirect("/")


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route("/mark_feedback_read/<int:feedback_id>", methods=["POST"])
def mark_feedback_read_route(feedback_id):
    if not session.get("authenticated"):
        return redirect("/login")
    
    feedback.mark_as_read(feedback_id)
    return redirect("/")

# ============================================
# MANAGER DETAIL PAGE
# ============================================

# HTML Template for Manager Detail Page
MANAGER_DETAIL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Manager {{ manager.id }} - BridgeOS Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }
        .header-left {
            flex: 1;
        }
        .header-left h1 { 
            font-size: 28px; 
            margin-bottom: 8px; 
        }
        .header-left p { 
            opacity: 0.9; 
            font-size: 14px; 
            margin: 0;
        }
        .header-right {
            display: flex;
            flex-direction: column;
            gap: 10px;
            align-items: flex-end;
        }
        .back-btn, .logout {
            background: rgba(255,255,255,0.2);
            color: white;
            padding: 8px 16px;
            border-radius: 5px;
            text-decoration: none;
            font-size: 14px;
            white-space: nowrap;
        }
        .back-btn:hover, .logout:hover { 
            background: rgba(255,255,255,0.3); 
        }
        .section {
            background: white;
            padding: 25px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .section h2 {
            font-size: 20px;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }
        .info-item {
            padding: 10px 0;
        }
        .info-item label {
            display: block;
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        .info-item value {
            display: block;
            font-size: 16px;
            color: #333;
            font-weight: 500;
        }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        .badge.connected { background: #48bb78; color: white; }
        .badge.disconnected { background: #f56565; color: white; }
        .badge.subscribed { background: #4299e1; color: white; }
        .message {
            padding: 12px;
            margin: 8px 0;
            font-size: 13px;
            border-left: 4px solid #ddd;
            background: #f9f9f9;
            border-radius: 4px;
        }
        .message.from-manager { border-left-color: #667eea; }
        .message.from-worker { border-left-color: #48bb78; }
        .message-meta {
            font-size: 11px;
            color: #999;
            margin-bottom: 5px;
        }
        .message-text {
            color: #333;
            word-wrap: break-word;
        }
        .btn {
            display: inline-block;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-size: 14px;
            border: none;
            cursor: pointer;
            margin-right: 10px;
            margin-bottom: 10px;
        }
        .btn:hover { background: #5568d3; }
        .btn.danger { background: #f56565; }
        .btn.danger:hover { background: #e53e3e; }
        .btn.secondary { background: #718096; }
        .btn.secondary:hover { background: #4a5568; }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
        .collapsible-header {
            cursor: pointer;
            user-select: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .collapsible-header:hover {
            color: #667eea;
        }
        .collapsible-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }
        .collapsible-content.expanded {
            max-height: 10000px;
        }
        .toggle-icon {
            font-size: 20px;
            transition: transform 0.3s ease;
        }
        .toggle-icon.expanded {
            transform: rotate(180deg);
        }
        .filter-buttons {
            margin-bottom: 20px;
        }
        .filter-btn {
            display: inline-block;
            padding: 8px 16px;
            background: #e2e8f0;
            color: #333;
            border: none;
            border-radius: 5px;
            font-size: 13px;
            cursor: pointer;
            margin-right: 10px;
            margin-bottom: 10px;
        }
        .filter-btn:hover { background: #cbd5e0; }
        .filter-btn.active { background: #667eea; color: white; }
        .message-count {
            font-size: 14px;
            color: #666;
            margin-bottom: 15px;
        }
    </style>
    <script>
        function toggleCollapsible(id) {
            const content = document.getElementById(id);
            const icon = document.getElementById(id + '-icon');
            content.classList.toggle('expanded');
            icon.classList.toggle('expanded');
        }
        
        function filterMessages(hours) {
            // This is a placeholder for future filtering functionality
            // For now, we'll reload the page with a query parameter
            window.location.href = '/manager/{{ manager.id }}?hours=' + hours;
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>👤 Manager Details</h1>
                <p>Manager ID: {{ manager.id }}</p>
            </div>
            <div class="header-right">
                <a href="/" class="back-btn">← Back to Dashboard</a>
                <a href="/logout" class="logout">🚪 Logout</a>
            </div>
        </div>

        <!-- Section 1: Manager Info -->
        <div class="section">
            <h2>📋 Manager Information</h2>
            <div class="info-grid">
                <div class="info-item">
                    <label>Manager ID</label>
                    <value>{{ manager.id }}</value>
                </div>
                <div class="info-item">
                    <label>Invitation Code</label>
                    <value>{{ manager.code }}</value>
                </div>
                <div class="info-item">
                    <label>Language</label>
                    <value>{{ manager.language }}</value>
                </div>
                <div class="info-item">
                    <label>Gender</label>
                    <value>{{ manager.gender }}</value>
                </div>
                <div class="info-item">
                    <label>Industry</label>
                    <value>{{ manager.industry }}</value>
                </div>
            </div>
        </div>

        <!-- Section 2: Connection & Subscription -->
        <div class="section">
            <h2>🔗 Connection & Subscription</h2>
            <div class="info-grid">
                <div class="info-item">
                    <label>Worker Status</label>
                    <value>
                        {% if worker %}
                            <span class="badge connected">✅ Connected</span>
                        {% else %}
                            <span class="badge disconnected">❌ No Worker</span>
                        {% endif %}
                    </value>
                </div>
                {% if worker %}
                <div class="info-item">
                    <label>Worker ID</label>
                    <value>{{ worker.id }}</value>
                </div>
                <div class="info-item">
                    <label>Worker Language</label>
                    <value>{{ worker.language }}</value>
                </div>
                {% endif %}
                <div class="info-item">
                    <label>Messages Sent</label>
                    <value>
                        {% if manager.subscription %}
                            Unlimited
                        {% else %}
                            {{ manager.messages_sent }} / {{ manager.message_limit }}
                            {% if manager.blocked %}
                                <span class="badge disconnected">🚫 Blocked</span>
                            {% endif %}
                        {% endif %}
                    </value>
                </div>
                <div class="info-item">
                    <label>Subscription</label>
                    <value>
                        {% if manager.subscription %}
                            <span class="badge subscribed">💳 {{ manager.subscription.status|title }}</span>
                        {% else %}
                            <span class="badge disconnected">Free Tier</span>
                        {% endif %}
                    </value>
                </div>
                {% if manager.subscription and manager.subscription.renews_at %}
                <div class="info-item">
                    <label>Renews At</label>
                    <value>{{ manager.subscription.renews_at[:10] }}</value>
                </div>
                {% endif %}
            </div>
            {% if manager.subscription and manager.subscription.customer_portal_url %}
            <div style="margin-top: 15px;">
                <a href="{{ manager.subscription.customer_portal_url }}" target="_blank" class="btn">🔗 Customer Portal</a>
            </div>
            {% endif %}
        </div>

        <!-- Section 3: Translation Context (Last 6 Messages) -->
        <div class="section">
            <h2>💬 Translation Context (Last 6 Messages)</h2>
            <p style="font-size: 13px; color: #666; margin-bottom: 15px;">
                These are the messages the bot uses for contextual translation.
            </p>
            {% if translation_context %}
                {% for msg in translation_context %}
                <div class="message {{ 'from-manager' if msg.is_manager else 'from-worker' }}">
                    <div class="message-meta">
                        <strong>{{ msg.from_role }}</strong> • {{ msg.time }} • {{ msg.lang }}
                    </div>
                    <div class="message-text">{{ msg.text }}</div>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty-state">
                    <p>No translation context available yet.</p>
                    <p style="font-size: 12px; margin-top: 10px;">Messages will appear here once the manager and worker start chatting.</p>
                </div>
            {% endif %}
        </div>

        <!-- Section 4: Full Message History -->
        <div class="section">
            <div class="collapsible-header" onclick="toggleCollapsible('full-history')">
                <h2>📜 Full Message History ({{ message_count }} messages)</h2>
                <span class="toggle-icon" id="full-history-icon">▼</span>
            </div>
            <div id="full-history" class="collapsible-content">
                <p style="font-size: 13px; color: #666; margin-bottom: 15px; margin-top: 15px;">
                    Complete conversation history (last 30 days).
                </p>
                
                <!-- Filter buttons (placeholder for future) -->
                <div class="filter-buttons">
                    <button class="filter-btn active" onclick="filterMessages('all')">All Messages</button>
                    <button class="filter-btn" onclick="filterMessages(24)">Last 24 Hours</button>
                    <button class="filter-btn" onclick="filterMessages(168)">Last 7 Days</button>
                    <button class="filter-btn" onclick="filterMessages(720)">Last 30 Days</button>
                </div>

                {% if full_history %}
                    <div class="message-count">Showing {{ full_history|length }} messages</div>
                    {% for msg in full_history %}
                    <div class="message {{ 'from-manager' if msg.is_manager else 'from-worker' }}">
                        <div class="message-meta">
                            <strong>{{ msg.from_role }}</strong> • {{ msg.timestamp }} • {{ msg.lang }}
                        </div>
                        <div class="message-text">{{ msg.text }}</div>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="empty-state">
                        <p>No message history available yet.</p>
                        <p style="font-size: 12px; margin-top: 10px;">Messages are stored for 30 days and will appear here.</p>
                    </div>
                {% endif %}
            </div>
        </div>

        <!-- Section 5: Admin Actions -->
        <div class="section">
            <h2>⚙️ Admin Actions</h2>
            <p style="font-size: 13px; color: #666; margin-bottom: 20px;">
                Manage this manager's account and data.
            </p>
            
            {% if manager.blocked %}
            <form method="POST" action="/reset_usage/{{ manager.id }}" style="display:inline;">
                <button type="submit" class="btn">🔓 Reset Usage Limit</button>
            </form>
            {% endif %}
            
            <form method="POST" action="/clear_translation_context/{{ manager.id }}" style="display:inline;"
                  onsubmit="return confirm('Clear translation context (last 6 messages)?');">
                <button type="submit" class="btn secondary">🧹 Clear Translation Context</button>
            </form>
            
            <form method="POST" action="/clear_full_history/{{ manager.id }}" style="display:inline;"
                  onsubmit="return confirm('Clear full message history (30 days)?');">
                <button type="submit" class="btn secondary">🗑️ Clear Full History</button>
            </form>
            
            <form method="POST" action="/delete_user/{{ manager.id }}" style="display:inline;" 
                  onsubmit="return confirm('Delete this manager and ALL their data? This cannot be undone!');">
                <button type="submit" class="btn danger">❌ Delete Manager Account</button>
            </form>
        </div>
    </div>
</body>
</html>
"""


# Route for Manager Detail Page
@app.route("/manager/<user_id>")
def manager_detail(user_id):
    # ...
    manager = database.get_user(user_id)
    manager["id"] = user_id
    
    # Get config
    config = load_config()
    message_limit = config.get("free_message_limit", 50)
    
    # Get usage stats
    usage = usage_tracker.get_usage(user_id)
    manager["messages_sent"] = usage.get("messages_sent", 0)  # ✅ FIXED
    
    # Get subscription status
    subscription = subscription_manager.get_subscription(user_id)
    manager["subscription"] = subscription  # ✅ FIXED
    
    # Only show blocked if NOT subscribed
    if subscription and subscription.get('status') in ['active', 'cancelled']:
        manager["blocked"] = False  # ✅ FIXED - Subscribed = never blocked
    else:
        manager["blocked"] = usage.get("blocked", False)  # ✅ FIXED - Check usage tracker
    
    manager["message_limit"] = message_limit  # ✅ FIXED
    
    # Get worker data (if connected)
    worker = None
    worker_id = manager.get("worker")


    # Get worker data (if connected)
    worker = None
    worker_id = manager.get("worker")
    if worker_id:
        worker = database.get_user(worker_id)
        if worker:
            worker["id"] = worker_id

    # Get translation context (last 6 messages)
    translation_context = []
    if worker_id:
        context_messages = translation_msg_context.get_conversation_history(
            user_id, worker_id, max_messages=6
        )
        for msg in context_messages:
            is_manager = msg["from"] == user_id
            translation_context.append(
                {
                    "time": datetime.fromisoformat(msg["timestamp"]).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "text": msg["text"],
                    "lang": msg["lang"],
                    "is_manager": is_manager,
                    "from_role": "Manager" if is_manager else "Worker",
                }
            )

    # Get full message history (last 30 days)
    full_history = []
    message_count = 0
    if worker_id:
        history_messages = message_history.get_messages(user_id, worker_id)
        message_count = len(history_messages)

        # Format messages for display
        for msg in history_messages:
            is_manager = msg["from"] == user_id
            full_history.append(
                {
                    "timestamp": datetime.fromisoformat(msg["timestamp"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "text": msg["text"],
                    "lang": msg["lang"],
                    "is_manager": is_manager,
                    "from_role": "Manager" if is_manager else "Worker",
                }
            )

    return render_template_string(
        MANAGER_DETAIL_HTML,
        manager=manager,
        worker=worker,
        translation_context=translation_context,
        full_history=full_history,
        message_count=message_count,
    )


# Additional admin action routes
@app.route("/clear_translation_context/<user_id>", methods=["POST"])
def clear_translation_context_route(user_id):
    """Clear translation context for a manager"""
    if not session.get("authenticated"):
        return redirect("/login")

    manager = database.get_user(user_id)
    if manager and manager.get("role") == "manager":
        worker_id = manager.get("worker")
        if worker_id:
            translation_msg_context.clear_conversation(user_id, worker_id)

    return redirect(f"/manager/{user_id}")


@app.route("/clear_full_history/<user_id>", methods=["POST"])
def clear_full_history_route(user_id):
    """Clear full message history for a manager"""
    if not session.get("authenticated"):
        return redirect("/login")

    manager = database.get_user(user_id)
    if manager and manager.get("role") == "manager":
        worker_id = manager.get("worker")
        if worker_id:
            message_history.clear_history(user_id, worker_id)

    return redirect(f"/manager/{user_id}")


if __name__ == "__main__":
    import os
    
    # ✅ Initialize connection pool before starting Flask
    db_connection.init_connection_pool(min_conn=5, max_conn=20)
    
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        # ✅ Clean shutdown: close all database connections
        db_connection.close_all_connections()