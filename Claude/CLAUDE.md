# BridgeOS - Claude.md

## What is BridgeOS?

BridgeOS is a Telegram bot enabling real-time translated communication between managers and foreign workers. It's an AI-powered workforce management system that translates conversations, generates daily action items, tracks tasks with "closed-loop" accountability, and converts unstructured reports into organized data.

**Core Features:**
- One-to-one translated conversations (manager ↔ worker)
- 12 languages with native scripts (English, עברית, العربية, ไทย, Español, Türkçe, Français, Deutsch, Português, Русский, हिन्दी, Filipino)
- Industry-specific terminology (8 industries: dairy, construction, restaurant, warehouse, nursing, hospitality, agriculture, general)
- Gender-aware grammar for Hebrew, Arabic, Spanish, French
- Media forwarding (photos, videos, voice, files)
- Task tracking with `**` prefix creates checkboxes
- AI-powered daily action items via `/daily` command
- Subscription management (8 free messages, then $9/month unlimited)
- Admin dashboard with manager detail pages

## Coding Principles

1. **KISS** - Simple, readable code. No fancy abstractions.
2. **Minimal** - Only what we need for MVP. No "what if" features.
3. **Smart structure** - Clean separation so we can swap parts later:
   - Translation logic → separate module (easy to swap providers)
   - Database → PostgreSQL with JSON storage
   - Payment logic → separate module (Lemon Squeezy)
   - Task tracking → separate module
   - Message storage → Two tables (translation context vs full history)
   - Dashboard → Two-page design (overview + detail)

## File Structure

```
bridgeos/
├── bot.py                      # Main bot logic (handlers, commands)
├── translator.py               # Translation (Claude/Gemini/OpenAI) + action items
├── database.py                 # PostgreSQL interface
├── translation_msg_context.py  # Last 6 messages for translation
├── message_history.py          # Full 30-day history for action items
├── usage_tracker.py            # Message limit tracking
├── subscription_manager.py     # Subscription CRUD
├── tasks.py                    # Task tracking CRUD
├── dashboard.py                # Flask admin + Lemon Squeezy webhooks
├── config.py                   # Configuration loader
├── i18n.py                     # i18n (lazy loading + caching)
├── config.json                 # Non-secret settings
├── secrets.json                # API keys (LOCAL only, .gitignore)
├── locales/                    # JSON translations per language
└── docs/                       # Documentation
```

## Separation of Concerns

### bot.py
- Telegram handlers only
- User registration (language → gender → industry)
- Deep-link invites (`/start invite_BRIDGE-12345`)
- Message routing (regular vs tasks)
- Task detection (`**` prefix)
- Subscription checking
- Commands: `/start`, `/help`, `/mycode`, `/tasks`, `/subscription`, `/daily`, `/refer`, `/reset`
- **NO** translation, database, payment, or config logic

### tasks.py
- Pure database CRUD for tasks
- Functions: `create_task()`, `complete_task()`, `get_manager_tasks()`, `get_worker_tasks()`
- **NO** translation, business rules, or Telegram API

### translator.py
- Provider-agnostic `translate()` function
- Accepts conversation history + industry for context
- `generate_daily_actionitems()` - Claude extracts action items in manager's language
- Provider implementations: Claude, Gemini, OpenAI

### database.py
- Simple interface: `get_user()`, `save_user()`, `get_all_users()`
- PostgreSQL with JSONB storage
- Tables: `users`, `translation_msg_context`, `message_history`, `usage_tracking`, `subscriptions`, `tasks`

### translation_msg_context.py
- Last 6 messages only (sliding window)
- Fast translation with recent context
- Pair-based keys: `"userID1_userID2"` (sorted)

### message_history.py
- Full 30-day conversation history
- For action items and analytics
- Auto-cleanup (deletes messages >30 days)

### subscription_manager.py
- Pure CRUD for subscriptions
- Functions: `get_subscription()`, `is_subscribed()`, `create_checkout_url()`
- **NO** webhook logic or HTTP

### dashboard.py
- Flask web app for admin monitoring
- Lemon Squeezy webhook handler (`/webhook/lemonsqueezy`)
- Two-page design: Overview (/) + Manager Details (/manager/{id})
- Password protected

### config.py
- Single source of truth
- Reads from: `config.json` (settings), `secrets.json` (local), environment variables (Railway)

## Key User Flows

### Manager Registration
```
/start → Select language → Select gender → Select industry
→ Receives invitation code (BRIDGE-12345) + deep-link
→ Taps share button → Sends to worker
```

### Worker Registration
```
Receives deep-link → /start invite_BRIDGE-12345
→ Select language → Select gender → ✅ Auto-connected!
```

### Communication Flow
```
Manager: "Check cow 115 for heat"
→ Bot checks subscription (unlimited if subscribed)
→ If not subscribed: Check free tier (8 messages)
→ Retrieves last 6 messages for context
→ Translates with industry context + gender + history
→ Worker receives: "בדוק את פרה 115 אם היא במחזור" (Hebrew, male form)
→ Saves to BOTH tables (translation_msg_context + message_history)
→ Increments counter if not subscribed
```

### Task Tracking Flow
```
Manager: ** Check cow 115 for heat
→ Bot detects ** prefix → Creates task
→ Translates to worker's language
→ Saves to tasks table (status: pending)
→ Worker receives with [✅ Mark Done] button
→ Worker clicks → Updates to completed
→ Manager receives completion notification
```

### Daily Action Items Flow
```
Manager: /daily
→ Bot retrieves last 24 hours from message_history
→ Claude extracts action items (NOT summaries)
→ Output in manager's language
→ Returns: Bullet-list of tasks, safety issues, equipment problems
```

## Configuration

**config.json** (safe to upload):
```json
{
  "translation_provider": "claude",
  "translation_context_size": 3,
  "message_retention_days": 30,
  "free_message_limit": 8,
  "enforce_limits": true,
  "testing_mode": true,
  "test_user_ids": ["6425887398"],
  "claude": {
    "model": "claude-sonnet-4-20250514"
  }
}
```

**secrets.json** (LOCAL only):
```json
{
  "telegram_token": "...",
  "claude_api_key": "...",
  "lemonsqueezy_webhook_secret": "..."
}
```

## Database Schema

**PostgreSQL Tables:**
- `users` - User data (JSONB)
- `translation_msg_context` - Last 6 messages (JSONB)
- `message_history` - Full 30-day history (JSONB)
- `usage_tracking` - Message limits (JSONB)
- `subscriptions` - Payment data (JSONB)
- `tasks` - Task tracking (id, manager_id, worker_id, description, status, timestamps)

## Key Design Patterns

1. **Dual Storage** - Translation context (6 msgs) separate from full history (30 days)
2. **Task Prefix** - `**` at start of message creates tracked task
3. **Gender-Aware** - Translations respect grammatical gender
4. **Industry Context** - Manager's industry passed to all translations
5. **Deep-Links** - One-tap worker invitations (no copy-paste)
6. **Freemium** - 8 free messages, then $9/month unlimited
7. **Testing Whitelist** - Specific users bypass limits
8. **Manager Language** - Action items ALWAYS in manager's registered language
9. **Anti-Summarization** - `/daily` extracts items, never summarizes

## Commands

**Manager:**
- `/start` - Register and get invitation
- `/tasks` - View pending/completed tasks
- `/daily` - Get action items (last 24h)
- `/subscription` - Manage subscription
- `/reset` - Delete account

**Worker:**
- `/start invite_BRIDGE-12345` - Connect via deep-link
- `/tasks` - View their tasks
- `/reset` - Delete account

## Railway Deployment

**Services:**
1. `worker` - Runs `bot.py`
2. `web` - Runs `dashboard.py`
3. PostgreSQL - Shared database

**Environment Variables:**
- `TELEGRAM_TOKEN`, `CLAUDE_API_KEY`, `DATABASE_URL`, `LEMONSQUEEZY_WEBHOOK_SECRET`

**Procfile:**
```
web: python dashboard.py
worker: python bot.py
```

## Important Constraints

1. **One worker per manager** (MVP only)
2. **Manager = anyone without invite code**
3. **Worker = anyone with invite deep-link**
4. **Gender required** for translation accuracy
5. **Usage tracking by Telegram ID** (survives resets)
6. **Subscribed users bypass all limits**
7. **Action items for managers only**
8. **Tasks use `**` prefix** (two stars)
9. **Workers complete tasks** (only)

## Testing Checklist

**Task Creation:**
- Manager sends `** Check cow 115`
- Manager receives confirmation
- Worker receives in their language with [✅ Mark Done]
- Saved to PostgreSQL (status: pending)

**Task Completion:**
- Worker clicks [✅ Mark Done]
- Updates to completed
- Manager receives notification

**Daily Action Items:**
- Multiple messages sent
- Manager types `/daily`
- Returns bullet-list (NOT summary)
- In manager's language

**Subscription:**
- Send 8 messages → See limit
- Subscribe → Unlimited
- `/subscription` → Shows status
- Cancel → Keeps access until ends_at

---

**Last Updated:** December 29, 2025  
**Version:** 3.3 (Task tracking complete)