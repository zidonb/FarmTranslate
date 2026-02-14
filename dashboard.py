from flask import Flask, render_template_string, request, redirect, session, jsonify
from config import load_config
from datetime import datetime, timezone
import secrets
import hmac
import hashlib
import requests
import os

import models.user as user_model
import models.manager as manager_model
import models.worker as worker_model
import models.connection as connection_model
import models.message as message_model
import models.subscription as subscription_model
import models.usage as usage_model
import models.feedback as feedback_model
from utils.db_connection import init_connection_pool, close_all_connections

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# CSRF Protection
def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

def verify_csrf_token(token):
    """Verify CSRF token matches session"""
    return token and token == session.get('csrf_token')

# Simple password protection
DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD')
if not DASHBOARD_PASSWORD:
    raise Exception("DASHBOARD_PASSWORD environment variable not set. Please set it in Railway dashboard.")

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
            print(f"Notification sent to {chat_id}")
        else:
            print(f"Failed to send notification: {response.text}")
    except Exception as e:
        print(f"Error sending notification: {e}")

@app.route("/webhook/lemonsqueezy", methods=["POST"])
def lemonsqueezy_webhook():
    """Handle Lemon Squeezy webhook events"""
    try:
        config = load_config()
        webhook_secret = config["lemonsqueezy"]["webhook_secret"]
        payload_body = request.get_data()
        signature_header = request.headers.get("X-Signature")

        if not signature_header:
            return jsonify({"error": "No signature"}), 401
        if not verify_signature(payload_body, signature_header, webhook_secret):
            return jsonify({"error": "Invalid signature"}), 401

        data = request.json
        event_name = data["meta"]["event_name"]
        custom_data = data["meta"].get("custom_data", {})
        telegram_id = custom_data.get("telegram_id")

        if not telegram_id:
            print(f"WARNING: No telegram_id in webhook for event {event_name}")
            return jsonify({"status": "success", "note": "no telegram_id"}), 200

        telegram_id = int(telegram_id)
        print(f"Processing event: {event_name} for telegram_id: {telegram_id}")

        handler_map = {
            "subscription_created": handle_subscription_created,
            "subscription_updated": handle_subscription_updated,
            "subscription_cancelled": handle_subscription_cancelled,
            "subscription_resumed": handle_subscription_resumed,
            "subscription_expired": handle_subscription_expired,
            "subscription_paused": handle_subscription_paused,
            "subscription_unpaused": handle_subscription_unpaused,
            "subscription_payment_success": handle_subscription_payment_success,
            "subscription_payment_failed": handle_subscription_payment_failed,
            "subscription_payment_recovered": handle_subscription_payment_recovered,
        }
        handler = handler_map.get(event_name)
        if handler:
            handler(telegram_id, data)
        else:
            print(f"Unhandled event: {event_name}")

        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"ERROR processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200

def handle_subscription_created(telegram_id: int, data: dict):
    attrs = data["data"]["attributes"]
    subscription_model.save(
        manager_id=telegram_id,
        external_id=str(data["data"]["id"]),
        status="active",
        customer_portal_url=attrs["urls"]["customer_portal"],
        renews_at=attrs["renews_at"],
        ends_at=attrs.get("ends_at"),
    )
    usage_model.reset(telegram_id)
    send_telegram_notification(telegram_id,
        "✅ *Subscription Active!*\n\nYou now have unlimited messages.\nThank you for subscribing to BridgeOS! 🎉")

def handle_subscription_updated(telegram_id: int, data: dict):
    attrs = data["data"]["attributes"]
    subscription = subscription_model.get_by_manager(telegram_id)
    if not subscription:
        handle_subscription_created(telegram_id, data)
        return
    status = "cancelled" if attrs["cancelled"] else subscription['status']
    subscription_model.save(
        manager_id=telegram_id,
        external_id=subscription.get('external_id'),
        status=status,
        customer_portal_url=attrs["urls"]["customer_portal"],
        renews_at=attrs["renews_at"],
        ends_at=attrs.get("ends_at"),
    )

def handle_subscription_cancelled(telegram_id: int, data: dict):
    attrs = data["data"]["attributes"]
    subscription_model.update_status(manager_id=telegram_id, status="cancelled", ends_at=attrs.get("ends_at"))
    ends_at_display = (attrs.get("ends_at", "end of billing period")[:10]
                       if attrs.get("ends_at") else "end of billing period")
    send_telegram_notification(telegram_id,
        f"⚠️ *Subscription Cancelled*\n\nYou'll keep access until {ends_at_display}.\nYou can resubscribe anytime.")

def handle_subscription_resumed(telegram_id: int, data: dict):
    subscription_model.update_status(manager_id=telegram_id, status="active", ends_at=None)
    usage_model.unblock(telegram_id)
    send_telegram_notification(telegram_id,
        "✅ *Subscription Resumed!*\n\nYour subscription is active again.\nWelcome back! 🎉")

def handle_subscription_expired(telegram_id: int, data: dict):
    subscription_model.update_status(manager_id=telegram_id, status="expired")
    usage = usage_model.get(telegram_id)
    config = load_config()
    free_limit = config.get('free_message_limit', 50)
    if usage and usage.get('messages_sent', 0) >= free_limit:
        usage_model.block(telegram_id)
    send_telegram_notification(telegram_id,
        "❌ *Subscription Expired*\n\nYour subscription has ended.\nYou're back on the free tier (50 messages).\n\nSubscribe again to continue unlimited messaging.")

def handle_subscription_paused(telegram_id: int, data: dict):
    subscription_model.update_status(manager_id=telegram_id, status="paused")

def handle_subscription_unpaused(telegram_id: int, data: dict):
    subscription_model.update_status(manager_id=telegram_id, status="active")

def handle_subscription_payment_success(telegram_id: int, data: dict):
    print(f"Payment successful for {telegram_id}")

def handle_subscription_payment_failed(telegram_id: int, data: dict):
    subscription = subscription_model.get_by_manager(telegram_id)
    portal_url = subscription.get("customer_portal_url") if subscription else None
    message = "⚠️ *Payment Failed*\n\nYour last payment didn't go through.\nWe'll retry automatically in 3 days.\n\n"
    if portal_url:
        message += f"Update your payment method: {portal_url}"
    send_telegram_notification(telegram_id, message)

def handle_subscription_payment_recovered(telegram_id: int, data: dict):
    subscription = subscription_model.get_by_manager(telegram_id)
    if subscription and subscription["status"] == "paused":
        subscription_model.update_status(manager_id=telegram_id, status="active")
    usage_model.unblock(telegram_id)

# ============================================
# HTML TEMPLATES
# ============================================
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
        .badge.pending { background: #ed8936; color: white; }
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
        .workers-list {
            margin: 10px 0;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 5px;
        }
        .worker-item {
            padding: 5px 0;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a href="/logout" class="logout">ðŸšª Logout</a>
            <h1>ðŸŒ‰ BridgeOS Dashboard</h1>
            <p>Real-time monitoring â€¢ Auto-refresh every 30 seconds â€¢ Last updated: {{ now }}</p>
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
            <h2>ðŸ‘” Managers</h2>
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
                                <span class="badge disconnected">ðŸš« Blocked</span>
                            {% else %}
                                <span class="badge connected">âœ“ Active</span>
                            {% endif %}
                        </div>
                        <div>
                            <strong>Subscription:</strong>
                            {% if manager.subscription %}
                                <span class="badge subscribed">ðŸ’³ {{ manager.subscription.status|title }}</span>
                            {% else %}
                                <span class="badge disconnected">Free Tier</span>
                            {% endif %}
                        </div>
                    </div>
                    
                    <!-- âœ… NEW: Multi-Worker Display -->
                    <div style="margin-top: 15px;">
                        <strong>Workers ({{ manager.worker_count }} connected{% if manager.pending_count > 0 %}, {{ manager.pending_count }} pending{% endif %}):</strong>
                        {% if manager.workers_display %}
                            <div class="workers-list">
                                {% for worker_info in manager.workers_display %}
                                <div class="worker-item">
                                    â€¢ Bot {{ worker_info.bot_id|upper }}: Worker {{ worker_info.worker_id }} 
                                    <span class="badge connected">{{ worker_info.status|title }}</span>
                                </div>
                                {% endfor %}
                                {% if manager.pending_bots %}
                                    {% for bot_id in manager.pending_bots %}
                                    <div class="worker-item">
                                        â€¢ Bot {{ bot_id|upper }}: <span class="badge pending">â³ Pending Invitation</span>
                                    </div>
                                    {% endfor %}
                                {% endif %}
                            </div>
                        {% else %}
                            <div class="workers-list">
                                <div class="worker-item" style="color: #999;">No workers connected yet</div>
                            </div>
                        {% endif %}
                    </div>
                    
                    <div class="actions">
                        <a href="/manager/{{ manager.id }}" class="btn">ðŸ‘ï¸ View Details</a>
                        <form method="POST" action="/delete_user/{{ manager.id }}" style="display:inline;" 
                              onsubmit="return confirm('Delete this manager and all their data?');">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn danger">ðŸ—‘ï¸ Delete Manager</button>
                        </form>
                        {% if manager.blocked %}
                        <form method="POST" action="/reset_usage/{{ manager.id }}" style="display:inline;">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn">ðŸ”„ Reset Usage</button>
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
            <h2>ðŸ‘·Workers</h2>
            {% if workers %}
                {% for worker in workers %}
                <div class="user-card worker">
                    <h3>Worker ID: {{ worker.id }}</h3>
                    <div class="user-info">
                        <div><strong>Language:</strong> {{ worker.language }}</div>
                        <div><strong>Gender:</strong> {{ worker.gender }}</div>
                        <div><strong>Manager:</strong> {{ worker.manager }}</div>
                        <div><strong>Bot ID:</strong> {{ worker.bot_id }}</div>
                    </div>
                    <div class="actions">
                        <form method="POST" action="/delete_user/{{ worker.id }}" style="display:inline;"
                            onsubmit="return confirm('Delete this worker?');">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn danger">ðŸ—‘ï¸ Delete Worker</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No workers registered yet.</p>
            {% endif %}
        </div>

        <div class="section">
            <h2>ðŸ’³ Subscriptions</h2>
            {% if subscriptions_list %}
                {% for sub in subscriptions_list %}
                <div class="user-card">
                    <h3>Telegram ID: {{ sub.telegram_id }}</h3>
                    <div class="user-info">
                        <div><strong>Status:</strong> 
                            {% if sub.status == 'active' %}
                                <span class="badge subscribed">âœ“ Active</span>
                            {% elif sub.status == 'cancelled' %}
                                <span class="badge disconnected">âš ï¸ Cancelled</span>
                            {% elif sub.status == 'expired' %}
                                <span class="badge disconnected">âŒ Expired</span>
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
                        <a href="{{ sub.customer_portal_url }}" target="_blank" class="btn">ðŸ”— Customer Portal</a>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No subscriptions yet.</p>
            {% endif %}
        </div>

        <div class="section">
            <h2>ðŸ’¬ Recent Conversations</h2>
            {% if conversations_list %}
                {% for conv in conversations_list %}
                <div class="conversation">
                    <h3>{{ conv.user1 }} â†” {{ conv.user2 }}</h3>
                    {% for msg in conv.messages %}
                    <div class="message {{ 'from-manager' if msg.is_manager else 'from-worker' }}">
                        <span class="message-time">{{ msg.time }}</span>
                        <strong>{{ msg.from_role }}:</strong> {{ msg.text }} <em>({{ msg.lang }})</em>
                    </div>
                    {% endfor %}
                    <div class="actions">
                        <form method="POST" action="/clear_conversation/{{ conv.key }}" style="display:inline;"
                              onsubmit="return confirm('Clear this conversation history?');">
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn danger">ðŸ§¹ Clear History</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No conversations yet.</p>
            {% endif %}
        </div>
        <div class="section">
            <h2>ðŸ’¬ User Feedback</h2>
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
                                <span class="badge connected">âœ… Read</span>
                            {% else %}
                                <span class="badge disconnected">â­• Unread</span>
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
                            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                            <button type="submit" class="btn">âœ… Mark as Read</button>
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
        <h1>ðŸŒ‰ BridgeOS</h1>
        <p>Dashboard Login</p>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>Password</label>
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <input type="password" name="password" placeholder="Enter dashboard password" required autofocus>
            </div>
            <button type="submit" class="btn">Login</button>
        </form>
    </div>
</body>
</html>
"""


# ============================================
# ROUTES
# ============================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if hmac.compare_digest(password.encode(), DASHBOARD_PASSWORD.encode()):
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

    config = load_config()
    message_limit = config.get("free_message_limit", 50)

    # ---- Managers ----
    all_managers = manager_model.get_all_active()
    managers = []
    for mgr in all_managers:
        manager_id = mgr['manager_id']
        user = user_model.get_by_id(manager_id)
        manager_data = {
            'id': manager_id,
            'code': mgr['code'],
            'language': mgr.get('language', user['language'] if user else 'Unknown'),
            'gender': user.get('gender', 'N/A') if user else 'N/A',
            'industry': mgr['industry'],
            'message_limit': message_limit,
        }
        usage = usage_model.get(manager_id)
        manager_data['messages_sent'] = usage['messages_sent'] if usage else 0
        subscription = subscription_model.get_by_manager(manager_id)
        manager_data['subscription'] = subscription
        if subscription and subscription.get('status') in ['active', 'cancelled']:
            manager_data['blocked'] = False
        else:
            manager_data['blocked'] = usage.get('is_blocked', False) if usage else False
        connections = connection_model.get_active_for_manager(manager_id)
        workers_display = [
            {'worker_id': c['worker_id'], 'bot_id': f"bot{c['bot_slot']}", 'status': 'active'}
            for c in connections
        ]
        manager_data['workers_display'] = workers_display
        manager_data['worker_count'] = len(workers_display)
        manager_data['pending_bots'] = []
        manager_data['pending_count'] = 0
        managers.append(manager_data)

    # ---- Workers ----
    all_workers = worker_model.get_all_active()
    workers = [
        {'id': w['worker_id'], 'language': w.get('language', 'Unknown'),
         'gender': w.get('gender', 'N/A'), 'manager': w.get('manager_id', 'N/A'),
         'bot_id': f"bot{w['bot_slot']}" if w.get('bot_slot') else 'N/A'}
        for w in all_workers
    ]

    # ---- Conversations ----
    recent_conversations = message_model.get_recent_across_connections(limit_per_connection=10)
    conversations_list = []
    for conv in recent_conversations:
        formatted_messages = []
        for msg in conv['messages']:
            msg_time = msg['sent_at'].strftime("%H:%M") if msg['sent_at'] else "??:??"
            is_manager = msg['sender_id'] == conv['manager_id']
            formatted_messages.append({
                'time': msg_time,
                'text': msg['original_text'],
                'lang': '',
                'is_manager': is_manager,
                'from_role': 'Manager' if is_manager else 'Worker',
            })
        conversations_list.append({
            'key': f"{conv['connection_id']}",
            'user1': f"{conv['manager_name'] or conv['manager_id']}",
            'user2': f"{conv['worker_name'] or conv['worker_id']}",
            'messages': formatted_messages,
        })

    # ---- Subscriptions ----
    all_subscriptions = subscription_model.get_all()
    active_subscriptions = sum(1 for s in all_subscriptions if s.get('status') in ['active', 'cancelled'])
    subscriptions_list = []
    for sub in all_subscriptions:
        renews_str = sub['renews_at'].isoformat() if sub.get('renews_at') else None
        ends_str = sub['ends_at'].isoformat() if sub.get('ends_at') else None
        created_str = sub['created_at'].isoformat() if sub.get('created_at') else ''
        subscriptions_list.append({
            'telegram_id': sub['manager_id'], 'status': sub['status'], 'plan': 'monthly',
            'started_at': created_str, 'renews_at': renews_str, 'ends_at': ends_str,
            'cancelled_at': None, 'lemon_subscription_id': sub.get('external_id', 'N/A'),
            'customer_portal_url': sub.get('customer_portal_url'),
        })

    # ---- Feedback ----
    feedback_list = [
        {'id': fb['feedback_id'], 'telegram_user_id': fb['user_id'],
         'user_name': fb.get('telegram_name', 'Unknown'), 'username': fb.get('username'),
         'message': fb.get('message', ''), 'created_at': fb.get('created_at'),
         'status': fb.get('status', 'unread')}
        for fb in feedback_model.get_all(limit=50)
    ]

    # ---- Stats ----
    all_active_connections = connection_model.get_all_active()
    stats = {
        'total_managers': len(managers), 'total_workers': len(workers),
        'active_connections': len(all_active_connections),
        'total_messages': message_model.get_total_count(),
        'total_subscriptions': active_subscriptions,
    }

    return render_template_string(
        DASHBOARD_HTML, managers=managers, workers=workers,
        conversations_list=conversations_list, subscriptions_list=subscriptions_list,
        feedback_list=feedback_list, stats=stats,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if not session.get("authenticated"):
        return redirect("/login")
    csrf_token = request.form.get('csrf_token')
    if not verify_csrf_token(csrf_token):
        return "Invalid CSRF token", 403

    user = user_model.get_by_id(user_id)
    if not user:
        return redirect("/")

    role = manager_model.get_role(user_id)
    if role == 'manager':
        connections = connection_model.get_active_for_manager(user_id)
        for conn in connections:
            connection_model.disconnect(conn['connection_id'])
            worker_model.soft_delete(conn['worker_id'])
        manager_model.soft_delete(user_id)
    elif role == 'worker':
        conn = connection_model.get_active_for_worker(user_id)
        if conn:
            connection_model.disconnect(conn['connection_id'])
        worker_model.soft_delete(user_id)

    user_model.delete(user_id)
    return redirect("/")

@app.route("/clear_conversation/<int:connection_id>", methods=["POST"])
def clear_conversation_route(connection_id):
    if not session.get("authenticated"):
        return redirect("/login")
    csrf_token = request.form.get('csrf_token')
    if not verify_csrf_token(csrf_token):
        return "Invalid CSRF token", 403
    message_model.delete_for_connection(connection_id)
    return redirect("/")

@app.route("/reset_usage/<int:user_id>", methods=["POST"])
def reset_usage_route(user_id):
    if not session.get("authenticated"):
        return redirect("/login")
    csrf_token = request.form.get('csrf_token')
    if not verify_csrf_token(csrf_token):
        return "Invalid CSRF token", 403
    usage_model.reset(user_id)
    return redirect("/")

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route("/mark_feedback_read/<int:feedback_id>", methods=["POST"])
def mark_feedback_read_route(feedback_id):
    if not session.get("authenticated"):
        return redirect("/login")
    csrf_token = request.form.get('csrf_token')
    if not verify_csrf_token(csrf_token):
        return "Invalid CSRF token", 403
    feedback_model.mark_as_read(feedback_id)
    return redirect("/")

# ============================================
# MANAGER DETAIL PAGE
# ============================================
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
        .badge.pending { background: #ed8936; color: white; }
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
        .workers-list {
            margin: 15px 0;
            padding: 15px;
            background: #f0f0f0;
            border-radius: 5px;
        }
        .worker-item {
            padding: 8px 0;
            font-size: 14px;
            border-bottom: 1px solid #ddd;
        }
        .worker-item:last-child {
            border-bottom: none;
        }
        .worker-selector {
            margin: 20px 0;
        }
        .worker-tab {
            display: inline-block;
            padding: 10px 20px;
            margin-right: 10px;
            background: #e2e8f0;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        .worker-tab:hover {
            background: #cbd5e0;
        }
        .worker-tab.active {
            background: #667eea;
            color: white;
        }
        .worker-section {
            display: none;
        }
        .worker-section.active {
            display: block;
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
        
        function showWorkerSection(workerId) {
            // Hide all worker sections
            document.querySelectorAll('.worker-section').forEach(section => {
                section.classList.remove('active');
            });
            
            // Remove active class from all tabs
            document.querySelectorAll('.worker-tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected worker section
            const section = document.getElementById('worker-' + workerId);
            if (section) {
                section.classList.add('active');
            }
            
            // Mark selected tab as active
            const tab = document.getElementById('tab-' + workerId);
            if (tab) {
                tab.classList.add('active');
            }
        }
        
        // Show first worker by default on page load
        window.addEventListener('DOMContentLoaded', function() {
            const firstTab = document.querySelector('.worker-tab');
            if (firstTab) {
                firstTab.click();
            }
        });
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>ðŸ‘¤ Manager Details</h1>
                <p>Manager ID: {{ manager.id }}</p>
            </div>
            <div class="header-right">
                <a href="/" class="back-btn">â† Back to Dashboard</a>
                <a href="/logout" class="logout">ðŸšª Logout</a>
            </div>
        </div>

        <!-- Section 1: Manager Info -->
        <div class="section">
            <h2>ðŸ“‹ Manager Information</h2>
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
            <h2>ðŸ”— Connection & Subscription</h2>
            <div class="info-grid">
                <div class="info-item">
                    <label>Workers Status</label>
                    <value>
                        {% if workers_list %}
                            {{ workers_list|length }} Connected
                        {% else %}
                            <span class="badge disconnected">âŒ No Workers</span>
                        {% endif %}
                    </value>
                </div>
                <div class="info-item">
                    <label>Messages Sent</label>
                    <value>
                        {% if manager.subscription %}
                            Unlimited
                        {% else %}
                            {{ manager.messages_sent }} / {{ manager.message_limit }}
                            {% if manager.blocked %}
                                <span class="badge disconnected">ðŸš« Blocked</span>
                            {% endif %}
                        {% endif %}
                    </value>
                </div>
                <div class="info-item">
                    <label>Subscription</label>
                    <value>
                        {% if manager.subscription %}
                            <span class="badge subscribed">ðŸ’³ {{ manager.subscription.status|title }}</span>
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
            
            <!-- âœ… NEW: Workers List -->
            {% if workers_list or pending_bots %}
            <div style="margin-top: 20px;">
                <label style="font-size: 14px; color: #666; text-transform: uppercase; margin-bottom: 10px; display: block;">
                    Workers ({{ workers_list|length }} connected{% if pending_bots %}, {{ pending_bots|length }} pending{% endif %})
                </label>
                <div class="workers-list">
                    {% for worker in workers_list %}
                    <div class="worker-item">
                        <strong>Bot {{ worker.bot_id|upper }}:</strong> 
                        Worker {{ worker.worker_id }} 
                        <span class="badge connected">{{ worker.status|title }}</span>
                        <br>
                        <small style="color: #666;">Language: {{ worker.language }}, Gender: {{ worker.gender }}</small>
                    </div>
                    {% endfor %}
                    
                    {% for bot_id in pending_bots %}
                    <div class="worker-item">
                        <strong>Bot {{ bot_id|upper }}:</strong> 
                        <span class="badge pending">â³ Pending Invitation</span>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}
            
            {% if manager.subscription and manager.subscription.customer_portal_url %}
            <div style="margin-top: 15px;">
                <a href="{{ manager.subscription.customer_portal_url }}" target="_blank" class="btn">ðŸ”— Customer Portal</a>
            </div>
            {% endif %}
        </div>

        <!-- Section 3: Translation Context (Per Worker) -->
        <div class="section">
            <h2>ðŸ’¬ Translation Context (Last 6 Messages Per Worker)</h2>
            <p style="font-size: 13px; color: #666; margin-bottom: 15px;">
                These are the messages the bot uses for contextual translation.
            </p>
            
            {% if workers_list %}
                <!-- Worker Tabs -->
                <div class="worker-selector">
                    {% for worker in workers_list %}
                    <div class="worker-tab" id="tab-{{ worker.worker_id }}" onclick="showWorkerSection('{{ worker.worker_id }}')">
                        Bot {{ worker.bot_id|upper }} - Worker {{ worker.worker_id }}
                    </div>
                    {% endfor %}
                </div>
                
                <!-- Worker Sections -->
                {% for worker in workers_list %}
                <div class="worker-section" id="worker-{{ worker.worker_id }}">
                    {% if worker.translation_context %}
                        {% for msg in worker.translation_context %}
                        <div class="message {{ 'from-manager' if msg.is_manager else 'from-worker' }}">
                            <div class="message-meta">
                                <strong>{{ msg.from_role }}</strong> â€¢ {{ msg.time }} â€¢ {{ msg.lang }}
                            </div>
                            <div class="message-text">{{ msg.text }}</div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="empty-state">
                            <p>No translation context available yet for this worker.</p>
                        </div>
                    {% endif %}
                </div>
                {% endfor %}
            {% else %}
                <div class="empty-state">
                    <p>No workers connected yet.</p>
                    <p style="font-size: 12px; margin-top: 10px;">Messages will appear here once the manager connects workers.</p>
                </div>
            {% endif %}
        </div>

        <!-- Section 4: Full Message History (Per Worker) -->
        <div class="section">
            <div class="collapsible-header" onclick="toggleCollapsible('full-history')">
                <h2>ðŸ“œ Full Message History ({{ total_message_count }} messages total)</h2>
                <span class="toggle-icon" id="full-history-icon">â–¼</span>
            </div>
            <div id="full-history" class="collapsible-content">
                <p style="font-size: 13px; color: #666; margin-bottom: 15px; margin-top: 15px;">
                    Complete conversation history (last 30 days).
                </p>
                
                {% if workers_list %}
                    <!-- Worker Tabs -->
                    <div class="worker-selector">
                        {% for worker in workers_list %}
                        <div class="worker-tab" onclick="showWorkerSection('history-{{ worker.worker_id }}')">
                            Bot {{ worker.bot_id|upper }} ({{ worker.message_count }} msgs)
                        </div>
                        {% endfor %}
                    </div>
                    
                    <!-- Worker History Sections -->
                    {% for worker in workers_list %}
                    <div class="worker-section" id="history-{{ worker.worker_id }}">
                        {% if worker.full_history %}
                            <div class="message-count">Showing {{ worker.full_history|length }} messages</div>
                            {% for msg in worker.full_history %}
                            <div class="message {{ 'from-manager' if msg.is_manager else 'from-worker' }}">
                                <div class="message-meta">
                                    <strong>{{ msg.from_role }}</strong> â€¢ {{ msg.timestamp }} â€¢ {{ msg.lang }}
                                </div>
                                <div class="message-text">{{ msg.text }}</div>
                            </div>
                            {% endfor %}
                        {% else %}
                            <div class="empty-state">
                                <p>No message history available yet for this worker.</p>
                            </div>
                        {% endif %}
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
            <h2>âš™ï¸ Admin Actions</h2>
            <p style="font-size: 13px; color: #666; margin-bottom: 20px;">
                Manage this manager's account and data.
            </p>
            
            {% if manager.blocked %}
            <form method="POST" action="/reset_usage/{{ manager.id }}" style="display:inline;">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="btn">ðŸ”“ Reset Usage Limit</button>
            </form>
            {% endif %}
            
            {% if workers_list %}
                {% for worker in workers_list %}
                <form method="POST" action="/clear_translation_context/{{ manager.id }}/{{ worker.connection_id }}" style="display:inline;"
                      onsubmit="return confirm('Clear translation context for Bot {{ worker.bot_id|upper }}?');">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button type="submit" class="btn secondary">ðŸ§¹ Clear Context (Bot {{ worker.bot_id|upper }})</button>
                </form>
                
                <form method="POST" action="/clear_full_history/{{ manager.id }}/{{ worker.connection_id }}" style="display:inline;"
                      onsubmit="return confirm('Clear full history for Bot {{ worker.bot_id|upper }}?');">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button type="submit" class="btn secondary">ðŸ—‘ï¸ Clear History (Bot {{ worker.bot_id|upper }})</button>
                </form>
                {% endfor %}
            {% endif %}
            
            <form method="POST" action="/delete_user/{{ manager.id }}" style="display:inline;" 
                  onsubmit="return confirm('Delete this manager and ALL their data? This cannot be undone!');">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="btn danger">âŒ Delete Manager Account</button>
            </form>
        </div>
    </div>
</body>
</html>
"""


@app.route("/manager/<int:user_id>")
def manager_detail(user_id):
    if not session.get("authenticated"):
        return redirect("/login")

    mgr = manager_model.get_by_id(user_id)
    if not mgr:
        return redirect("/")
    user = user_model.get_by_id(user_id)
    if not user:
        return redirect("/")

    config = load_config()
    message_limit = config.get("free_message_limit", 50)
    manager = {
        'id': user_id, 'code': mgr['code'], 'language': user['language'],
        'gender': user.get('gender', 'N/A'), 'industry': mgr['industry'],
        'message_limit': message_limit,
    }

    usage = usage_model.get(user_id)
    manager['messages_sent'] = usage['messages_sent'] if usage else 0
    subscription = subscription_model.get_by_manager(user_id)
    manager['subscription'] = subscription
    if subscription and subscription.get('status') in ['active', 'cancelled']:
        manager['blocked'] = False
    else:
        manager['blocked'] = usage.get('is_blocked', False) if usage else False

    connections = connection_model.get_active_for_manager(user_id)
    pending_bots = []
    workers_list = []
    total_message_count = 0

    for conn in connections:
        worker_user = user_model.get_by_id(conn['worker_id'])
        if not worker_user:
            continue
        worker_data = {
            'worker_id': conn['worker_id'], 'bot_id': f"bot{conn['bot_slot']}",
            'status': 'active', 'language': worker_user.get('language', 'Unknown'),
            'gender': worker_user.get('gender', 'N/A'), 'connection_id': conn['connection_id'],
        }

        # Translation context (last 6 messages)
        context_messages = message_model.get_translation_context(conn['connection_id'], limit=6)
        translation_context = []
        for msg in context_messages:
            is_manager = str(msg['from']) == str(user_id)
            sent_at = msg.get('timestamp')
            time_str = ''
            if sent_at:
                try:
                    dt = datetime.fromisoformat(sent_at) if isinstance(sent_at, str) else sent_at
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, AttributeError):
                    time_str = str(sent_at)
            translation_context.append({
                'time': time_str, 'text': msg['text'], 'lang': '',
                'is_manager': is_manager, 'from_role': 'Manager' if is_manager else 'Worker',
            })
        worker_data['translation_context'] = translation_context

        # Full message history
        all_messages = message_model.get_for_connection(conn['connection_id'])
        worker_data['message_count'] = len(all_messages)
        total_message_count += len(all_messages)
        full_history = []
        for msg in all_messages:
            is_manager = msg['sender_id'] == user_id
            sent_at = msg.get('sent_at')
            time_str = sent_at.strftime("%Y-%m-%d %H:%M:%S") if sent_at else ''
            full_history.append({
                'timestamp': time_str, 'text': msg['original_text'], 'lang': '',
                'is_manager': is_manager, 'from_role': 'Manager' if is_manager else 'Worker',
            })
        worker_data['full_history'] = full_history
        workers_list.append(worker_data)

    return render_template_string(
        MANAGER_DETAIL_HTML, manager=manager, workers_list=workers_list,
        pending_bots=pending_bots, total_message_count=total_message_count,
    )

@app.route("/clear_translation_context/<int:user_id>/<int:connection_id>", methods=["POST"])
def clear_translation_context_route(user_id, connection_id):
    """Clear translation context for a specific connection"""
    if not session.get("authenticated"):
        return redirect("/login")
    csrf_token = request.form.get('csrf_token')
    if not verify_csrf_token(csrf_token):
        return "Invalid CSRF token", 403
    if not manager_model.get_by_id(user_id):
        return redirect("/")
    message_model.delete_for_connection(connection_id)
    return redirect(f"/manager/{user_id}")

@app.route("/clear_full_history/<int:user_id>/<int:connection_id>", methods=["POST"])
def clear_full_history_route(user_id, connection_id):
    """Clear full message history for a specific connection"""
    if not session.get("authenticated"):
        return redirect("/login")
    csrf_token = request.form.get('csrf_token')
    if not verify_csrf_token(csrf_token):
        return "Invalid CSRF token", 403
    if not manager_model.get_by_id(user_id):
        return redirect("/")
    message_model.delete_for_connection(connection_id)
    return redirect(f"/manager/{user_id}")


if __name__ == "__main__":
    init_connection_pool(min_conn=1, max_conn=3)
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        close_all_connections()
