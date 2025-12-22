from flask import Flask, render_template_string, request, redirect, session, jsonify
import database
import conversations
from config import load_config
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Simple password protection
DASHBOARD_PASSWORD = "zb280072A"  # Change this!

# HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>FarmTranslate Dashboard</title>
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
            <h1>🚜 FarmTranslate Dashboard</h1>
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
                        <div>
                            <strong>Worker:</strong> 
                            {% if manager.worker %}
                                <span class="badge connected">✓ Connected ({{ manager.worker }})</span>
                            {% else %}
                                <span class="badge disconnected">✗ No Worker</span>
                            {% endif %}
                        </div>
                    </div>
                    <div class="actions">
                        <form method="POST" action="/delete_user/{{ manager.id }}" style="display:inline;" 
                              onsubmit="return confirm('Delete this manager and all their data?');">
                            <button type="submit" class="btn danger">🗑️ Delete Manager</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: #999;">No managers registered yet.</p>
            {% endif %}
        </div>

        <div class="section">
            <h2>👷 Workers</h2>
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
    </div>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>FarmTranslate Dashboard - Login</title>
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
        <h1>🚜 FarmTranslate</h1>
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == DASHBOARD_PASSWORD:
            session['authenticated'] = True
            return redirect('/')
        else:
            return render_template_string(LOGIN_HTML, error="Invalid password")
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def dashboard():
    # Check authentication
    if not session.get('authenticated'):
        return redirect('/login')
    
    # Get all users
    all_users = database.get_all_users()
    
    # Separate managers and workers
    managers = []
    workers = []
    
    for user_id, user_data in all_users.items():
        user_data['id'] = user_id
        if user_data.get('role') == 'manager':
            managers.append(user_data)
        elif user_data.get('role') == 'worker':
            workers.append(user_data)
    
    # Get all conversations
    all_conversations = conversations.load_conversations()
    conversations_list = []
    
    for conv_key, messages in all_conversations.items():
        user1, user2 = conv_key.split('_')
        
        # Get user info
        user1_data = database.get_user(user1)
        user2_data = database.get_user(user2)
        
        formatted_messages = []
        for msg in messages[-10:]:  # Last 10 messages
            msg_time = datetime.fromisoformat(msg['timestamp']).strftime('%H:%M')
            
            # Determine if from manager
            is_manager = False
            from_role = "User"
            if user1_data and user1_data.get('role') == 'manager' and msg['from'] == user1:
                is_manager = True
                from_role = "Manager"
            elif user2_data and user2_data.get('role') == 'manager' and msg['from'] == user2:
                is_manager = True
                from_role = "Manager"
            else:
                from_role = "Worker"
            
            formatted_messages.append({
                'time': msg_time,
                'text': msg['text'],
                'lang': msg['lang'],
                'is_manager': is_manager,
                'from_role': from_role
            })
        
        conversations_list.append({
            'key': conv_key,
            'user1': user1,
            'user2': user2,
            'messages': formatted_messages
        })
    
    # Calculate stats
    stats = {
        'total_managers': len(managers),
        'total_workers': len(workers),
        'active_connections': sum(1 for m in managers if m.get('worker')),
        'total_messages': sum(len(msgs) for msgs in all_conversations.values())
    }
    
    return render_template_string(
        DASHBOARD_HTML,
        managers=managers,
        workers=workers,
        conversations_list=conversations_list,
        stats=stats,
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )

@app.route('/delete_user/<user_id>', methods=['POST'])
def delete_user(user_id):
    # Check authentication
    if not session.get('authenticated'):
        return redirect('/login')
    
    user = database.get_user(user_id)
    if not user:
        return redirect('/')
    
    # If manager, also delete worker and conversation
    if user.get('role') == 'manager':
        worker_id = user.get('worker')
        if worker_id:
            # Delete conversation
            conversations.clear_conversation(user_id, worker_id)
            
            # Delete worker
            all_users = database.get_all_users()
            if worker_id in all_users:
                del all_users[worker_id]
                database.save_data(all_users)
    
    # If worker, update manager and clear conversation
    elif user.get('role') == 'worker':
        manager_id = user.get('manager')
        if manager_id:
            manager = database.get_user(manager_id)
            if manager:
                manager['worker'] = None
                database.save_user(manager_id, manager)
            
            conversations.clear_conversation(user_id, manager_id)
    
    # Delete the user
    all_users = database.get_all_users()
    if user_id in all_users:
        del all_users[user_id]
        database.save_data(all_users)
    
    return redirect('/')

@app.route('/clear_conversation/<conv_key>', methods=['POST'])
def clear_conversation_route(conv_key):
    # Check authentication
    if not session.get('authenticated'):
        return redirect('/login')
    
    user1, user2 = conv_key.split('_')
    conversations.clear_conversation(user1, user2)
    
    return redirect('/')

if __name__ == '__main__':
    import os
    import threading
    
    # Start bot in background thread
    def run_bot():
        import bot
        bot.main()
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start dashboard
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)