# FarmTranslate Dashboard Setup

## What I Created

1. **dashboard.py** - Flask web dashboard with:
   - Real-time data (auto-refresh every 30 seconds)
   - Password protection
   - Admin actions (delete users, clear conversations)
   - Beautiful responsive design

2. **Updated requirements.txt** - Added Flask

3. **Updated Procfile** - Runs both bot + dashboard

## Features

### 📊 Dashboard Sections:
- **Statistics**: Total managers, workers, active connections, message count
- **Managers**: List all managers with their codes, languages, connection status
- **Workers**: List all workers with their manager info
- **Conversations**: Show recent messages between manager-worker pairs

### 🔐 Security:
- Password protected login
- Default password: `farmadmin2024` (⚠️ **CHANGE THIS!**)

### ⚡ Admin Actions:
- Delete manager (also deletes their worker and conversation)
- Delete worker (disconnects from manager, clears conversation)
- Clear conversation history

## How to Deploy on Railway

### Step 1: Change Password
In `dashboard.py` line 14, change:
```python
DASHBOARD_PASSWORD = "farmadmin2024"  # Change this!
```

### Step 2: Deploy Files
Upload these files to your Railway project:
- ✅ dashboard.py
- ✅ requirements.txt (updated)
- ✅ Procfile (updated)

### Step 3: Railway Configuration
Railway will now run TWO services:
- **web** (dashboard) - Port 5000
- **worker** (bot) - Background process

Railway will give you a URL like:
`https://your-project.railway.app`

### Step 4: Access Dashboard
1. Go to your Railway URL
2. Login with password: `farmadmin2024` (or whatever you changed it to)
3. Done! Dashboard updates every 30 seconds automatically

## Local Testing

To test locally before deploying:

```bash
# Terminal 1 - Run bot
python bot.py

# Terminal 2 - Run dashboard
python dashboard.py
```

Then open: http://localhost:5000

## Screenshots

**Login Page:**
- Simple password entry
- Purple gradient background

**Dashboard:**
- Real-time stats at top
- Manager cards (purple border)
- Worker cards (green border)
- Conversation history with color-coded messages
- Delete buttons for each user
- Clear history buttons for conversations

## Security Notes

⚠️ **IMPORTANT:**
1. Change the default password immediately
2. Don't share the dashboard URL publicly
3. Consider adding IP whitelist if needed
4. The dashboard uses session-based authentication

## Auto-Refresh

The dashboard automatically refreshes every 30 seconds to show live data.
You can change this in the HTML meta tag:
```html
<meta http-equiv="refresh" content="30">
```

## Customization

Want to customize colors, layout, or features? All CSS is inline in `dashboard.py` - easy to modify!

## Troubleshooting

**Dashboard won't load:**
- Check Railway logs
- Make sure both services are running
- Verify PORT environment variable

**Can't login:**
- Check password in dashboard.py line 14
- Clear browser cookies
- Try incognito mode

**Data not showing:**
- Check users.json and conversations.json exist
- Verify bot is running and creating data
- Check file permissions on Railway