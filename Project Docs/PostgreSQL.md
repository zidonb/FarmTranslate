# PostgreSQL Migration Guide - KISS Approach

## What Changed

✅ **Simple upgrade**: JSON files → PostgreSQL with JSON storage
✅ **Same structure**: Still storing JSON, just in a database
✅ **Clean separation**: Bot and dashboard are separate services again
✅ **Shared data**: Both services access same PostgreSQL database

## Files to Update

1. **database.py** - Now uses PostgreSQL instead of users.json
2. **conversations.py** - Now uses PostgreSQL instead of conversations.json  
3. **requirements.txt** - Added psycopg2-binary (PostgreSQL driver)
4. **dashboard.py** - Clean version (no threading mess)
5. **Procfile** - Two separate services

## Railway Setup Steps

### Step 1: Add PostgreSQL Database

1. Go to your Railway project
2. Click **"+ Create"** → **"Database"** → **"Add PostgreSQL"**
3. Railway will automatically create `DATABASE_URL` environment variable
4. Both your services (web + worker) will have access to it automatically

### Step 2: Update Your Files

Upload these 5 files (replace old ones):
- ✅ database.py (new PostgreSQL version)
- ✅ conversations.py (new PostgreSQL version)
- ✅ requirements.txt (added psycopg2-binary)
- ✅ dashboard.py (clean, no threading)
- ✅ Procfile (two services)

### Step 3: Redeploy

Both services will:
- Install psycopg2-binary
- Connect to PostgreSQL
- Auto-create tables on first run
- Start working immediately

### Step 4: Verify

1. Register a new user via Telegram bot
2. Open dashboard URL
3. You should see: **Total Managers: 1** ✅

## What Happens on First Run

When each service starts, it automatically:
```python
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
)

CREATE TABLE IF NOT EXISTS conversations (
    conversation_key TEXT PRIMARY KEY,
    messages JSONB NOT NULL
)
```

No manual database setup needed! 🎉

## Architecture Now

```
┌─────────────────────┐
│   PostgreSQL DB     │
│  ┌──────────────┐   │
│  │ users table  │   │
│  │ conversations│   │
│  └──────────────┘   │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
┌────▼───┐  ┌───▼────┐
│ Worker │  │  Web   │
│ (bot)  │  │(dash)  │
└────────┘  └────────┘
```

Both services read/write to same database = shared data ✅

## Code Changes Summary

### database.py
- `load_data()` → SELECT from PostgreSQL
- `save_user()` → INSERT/UPDATE in PostgreSQL
- Still returns same dictionary format (no caller code changes needed)

### conversations.py
- `load_conversations()` → SELECT from PostgreSQL
- `add_to_conversation()` → INSERT/UPDATE in PostgreSQL
- Still returns same format (no caller code changes needed)

### bot.py & translator.py
- **NO CHANGES NEEDED** ✅
- They import database/conversations, which now use PostgreSQL under the hood

## Advantages

✅ **Shared data** - Both services access same data
✅ **No file locking** - PostgreSQL handles concurrency
✅ **Atomic writes** - No data corruption
✅ **Scalable** - Handles 50k+ users easily
✅ **Clean code** - No threading mess
✅ **KISS** - Simple upgrade, minimal changes

## Troubleshooting

**Error: "DATABASE_URL not found"**
- Make sure PostgreSQL is added in Railway
- Check Variables tab shows DATABASE_URL

**Error: "relation does not exist"**
- Tables create automatically on first import
- Check logs for initialization messages

**Dashboard shows 0 users but bot has users**
- Services might be using different databases
- Check both have same DATABASE_URL

**Want to see your data?**
Railway → PostgreSQL service → Query tab:
```sql
SELECT * FROM users;
SELECT * FROM conversations;
```

## Rollback Plan

If something goes wrong:
1. Stop new deployments
2. Revert to old database.py/conversations.py
3. Your JSON files are still there
4. Remove PostgreSQL from Railway

## Migration Complete! 🎉

Your bot now:
- ✅ Uses professional database
- ✅ Scales to 50k+ users
- ✅ Has clean, separate services
- ✅ Maintains KISS principle
- ✅ No threading complexity