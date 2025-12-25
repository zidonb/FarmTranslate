# BridgeOS - Architecture & Guidelines

---

## **What is BridgeOS?**

BridgeOS (formerly FarmTranslate) is a Telegram bot that enables real-time translated communication between managers and workers who speak different languages. Built initially for dairy farms with foreign workers, it now supports multiple industries through industry-specific translation contexts.

BridgeOS is an AI-powered Operating System designed to manage foreign workforces by transforming simple translation into operational control. It functions as a command center that not only translates communication in real-time but also automatically generates daily site summaries, tracks task completion with "closed-loop" accountability, and converts unstructured worker reports into organized data logs. By bridging the gap between instruction and execution, BridgeOS ensures that nothing—from safety hazards to critical tasks—gets lost in translation.

**Key Features:**
- One-to-one translated conversations (manager ↔ worker)
- Industry-specific terminology (dairy, construction, restaurant, warehouse, etc.)
- Gender-aware grammar for accurate translations in Hebrew, Arabic, Spanish, French
- Conversation history for contextual understanding
- Support for 12 languages (including native scripts)
- Deep-link invitations with one-tap sharing
- Real-time admin dashboard
- Media forwarding (photos, videos, voice messages, files)
- **Subscription management with Lemon Squeezy**
- **Usage tracking with free tier (50 messages) + unlimited paid tier**
- Telegram notifications for subscription events

---

## **Business Model**

### **Freemium + Subscription:**
- **Free Tier**: 50 messages per manager
- **Paid Tier**: $9/month for unlimited messages
- **Workers**: Always unlimited (free)

### **Payment Processing:**
- **Provider**: Lemon Squeezy (Merchant of Record)
- **Integration**: Webhook-based subscription lifecycle
- **Management**: Customer portal for cancellations, billing updates
- **Notifications**: Telegram messages for subscription events

---

## **User Flow**

### **Manager Registration:**
```
1. /start
2. Select language (English, עברית, العربية, ไทย, Español, etc.)
3. Select gender (Male, Female, Prefer not to say)
4. Select industry (Dairy Farm, Construction, Restaurant, etc.)
5. Receives invitation with:
   - Code (e.g., BRIDGE-12345) - 5 digits
   - Deep-link (https://t.me/FarmTranslateBot?start=invite_BRIDGE-12345)
   - Share button (opens chat picker with prefilled message)
6. Taps share button → selects worker → sends invitation
```

### **Worker Registration:**
```
1. Receives invitation link from manager
2. Taps link → /start invite_BRIDGE-12345 (code auto-extracted)
3. Select language
4. Select gender
5. ✅ Auto-connected! Can start chatting
```

### **Communication Flow:**
```
Manager types: "Check cow 115 for heat"
   ↓
Bot checks if user is subscribed (subscription_manager.is_subscribed())
   ↓
If subscribed: Allow message (unlimited)
If not subscribed: Check free tier limit (usage_tracker.is_user_blocked())
   ↓
If blocked: Show subscribe button with Lemon Squeezy checkout URL
   ↓
Bot retrieves conversation history from PostgreSQL
   ↓
Bot translates with industry context (dairy) + gender + history
   ↓
Worker receives: "בדוק את פרה 115 אם היא במחזור" (Hebrew, male form)
   ↓
Bot increments manager's message counter (if not subscribed)
   ↓
Worker replies: "היא נראית בריאה"
   ↓
Manager receives: "She looks healthy"
```

### **Subscription Journey:**
```
Manager sends 50th message
   ↓
Bot shows: "⚠️ You've reached the free limit (50 messages)"
           "💳 Subscribe to BridgeOS: $9/month"
           [💳 Subscribe ($9/month)] ← Button
   ↓
Manager clicks button → Opens Lemon Squeezy checkout
   ↓
Manager completes payment
   ↓
Lemon Squeezy sends webhook to: /webhook/lemonsqueezy
   ↓
dashboard.py processes webhook → Updates PostgreSQL
   ↓
Manager receives Telegram notification: "✅ Subscription Active!"
   ↓
Manager continues chatting (unlimited messages)
   ↓
Manager types: /subscription
   ↓
Bot shows: "📋 Your Subscription"
           "✅ Status: Active"
           "💳 Plan: Unlimited Messages"
           "💵 Price: $9/month"
           "📅 Renews: 2026-01-23"
           [⚙️ Manage Subscription] ← Opens Lemon Squeezy portal
   ↓
Manager clicks "Manage Subscription" → Can cancel, update payment, view invoices
   ↓
If cancelled: Keeps access until end of billing period
   ↓
On expiry: Receives notification, returns to free tier (50 messages)
```

---

## **Coding Principles**

1. **KISS** - Simple, readable code. No fancy abstractions.
2. **Minimal** - Only what we need for MVP. No "what if" features.
3. **Smart structure** - Clean separation so we can swap parts later:
   - Translation logic → separate module (easy to swap providers)
   - Database → PostgreSQL with JSON storage (scalable, shared data)
   - Bot handlers → clean functions (easy to add features)
   - Payment logic → separate module (easy to swap providers)
   - Configuration → centralized, secrets separate

---

## **File Structure**
```
bridgeos/
├── bot.py                      # Main bot logic (handlers, commands, deep-link support)
├── translator.py               # Translation with multiple LLM providers
├── database.py                 # PostgreSQL storage with clean interface
├── conversations.py            # Conversation history in PostgreSQL (sliding window)
├── usage_tracker.py            # Message limit tracking and enforcement
├── subscription_manager.py     # Subscription CRUD operations (database interface) ← NEW
├── dashboard.py                # Flask admin dashboard + Lemon Squeezy webhooks ← UPDATED
├── config.py                   # Configuration loader (environment + files)
├── config.json                 # Non-secret settings (safe to upload to GitHub) ← UPDATED
├── secrets.json                # API keys (LOCAL only, in .gitignore)
├── requirements.txt            # Python dependencies ← UPDATED
├── Procfile                    # Railway deployment (web + worker services)
├── runtime.txt                 # Python version (3.11.9)
├── .gitignore                  # Exclude secrets and data files
└── docs/                       # Documentation folder
    ├── BACKGROUND.md           # Project context for new sessions
    ├── structure.md            # This file ← UPDATED
    ├── POSTGRESQL_MIGRATION.md # Database migration guide
    ├── DASHBOARD_SETUP.md      # Dashboard setup instructions
    ├── DEPLOYMENT_CHECKLIST.md # Lemon Squeezy deployment guide ← NEW
    └── TESTING_GUIDE.md        # Payment testing procedures ← NEW
```

---

## **Design Pattern: Separation of Concerns**

### **bot.py**
- Telegram bot handlers
- User registration flow (language → gender → industry OR auto-connect via deep-link)
- Deep-link support (`/start invite_BRIDGE-12345`)
- InlineKeyboard share button with prefilled message
- Message routing logic
- Media forwarding (photos, videos, voice, files, stickers, locations, contacts)
- **Subscription checking before sending messages** ← NEW
- **Subscribe button generation with Lemon Squeezy checkout URL** ← NEW
- Usage limit enforcement (checks before sending, increments after)
- Commands: `/start`, `/help`, `/mycode`, `/subscription`, `/refer`, `/reset` ← UPDATED
- No translation, database, payment, or config logic

### **translator.py**
- Provider-agnostic `translate()` function
- Accepts conversation history and industry for context
- Provider-specific implementations:
  - `translate_with_claude()` - Strong system prompt with industry context
  - `translate_with_gemini()` - Schema-enforced JSON (prevents answering questions)
  - `translate_with_openai()` - System prompt approach
- `build_translation_prompt()` - Handles context, gender, industry

### **database.py**
- Simple function interface: `get_user()`, `save_user()`, `get_all_users()`
- PostgreSQL with JSONB storage (maintains same data structure as JSON files)
- Tables: `users`, `conversations`, `usage_tracking`, `subscriptions` ← UPDATED
- Shared access: Both bot and dashboard use same database

### **conversations.py**
- Conversation history management in PostgreSQL
- `get_conversation_history()` - Retrieve last N messages
- `add_to_conversation()` - Save message with sliding window
- `clear_conversation()` - Delete conversation history
- Pair-based keys: `"userID1_userID2"` (sorted, lowest first)
- Stores original language + text for better translation context
- Tables: `conversations` (conversation_key, messages)

### **usage_tracker.py**
- Message limit tracking and enforcement
- Tracks by Telegram user ID (survives account resets)
- Functions:
  - `get_usage()` - Get usage data for a user
  - `is_user_blocked()` - Check if user has reached limit
  - `increment_message_count()` - Count message and check limit
  - `reset_user_usage()` - Admin function to reset limits
  - `get_usage_stats()` - Aggregated statistics
- Tables: `usage_tracking` (telegram_user_id, data)
- Only tracks manager messages when not subscribed (workers unlimited)
- Configurable limit (default: 50 free messages)

### **subscription_manager.py** ← NEW
- **Database waiter** - Pure CRUD operations for subscriptions
- No webhook logic, no HTTP, no business logic
- Functions:
  - `get_subscription(telegram_id)` - Retrieve subscription data
  - `save_subscription(telegram_id, data)` - Upsert subscription
  - `is_subscribed(telegram_id)` - Check active access (handles cancelled-but-not-expired)
  - `create_checkout_url(telegram_id)` - Generate Lemon Squeezy checkout URL
  - `get_customer_portal_url(telegram_id)` - Get management portal link
  - `delete_subscription(telegram_id)` - Admin function
  - `get_all_subscriptions()` - For dashboard display
- Tables: `subscriptions` (telegram_user_id, data)
- **Separation principle**: Bot and dashboard both call subscription_manager, never duplicate logic

### **dashboard.py** ← UPDATED
- Flask web application for admin monitoring
- **Lemon Squeezy webhook handler** (`/webhook/lemonsqueezy`) ← NEW
- Real-time data from PostgreSQL (auto-refresh every 30s)
- Password protected (`zb280072A` - change this!)
- Features:
  - Statistics (total managers, workers, connections, messages, **subscriptions**) ← UPDATED
  - Manager list with codes, connection status, usage stats, and **subscription badges** ← NEW
  - Worker list with manager info
  - **Subscription list with status, plan, dates, portal links** ← NEW
  - Recent conversations
  - Admin actions (delete users, clear conversations, reset usage limits)
- **Webhook Processing**: ← NEW
  - Verifies HMAC-SHA256 signature
  - Processes 11 subscription event types
  - Updates PostgreSQL via subscription_manager
  - Sends Telegram notifications via Bot API
  - Always returns 200 OK (prevents retry storms)
- Usage tracking display: Shows messages sent / limit for each manager
- Reset usage button for blocked managers

### **config.py**
- Single source of truth for configuration
- Reads from:
  - `config.json` (non-secret settings)
  - `secrets.json` (local development)
  - Environment variables (Railway deployment)
- All other files import: `from config import load_config`

### **config.json** (Safe to upload) ← UPDATED
```json
{
  "translation_provider": "claude",
  "industries": {
    "dairy_farm": {
      "name": "Dairy Farm",
      "description": "Communication between dairy farm manager and workers..."
    },
    "construction": {
      "name": "Construction",
      "description": "Communication about construction site operations..."
    }
  },
  "history_size": 3,
  "free_message_limit": 50,
  "enforce_limits": true,
  "lemonsqueezy": {
    "store_url": "bridgeos.lemonsqueezy.com",
    "checkout_id": "61249267-2ffd-487f-b2e9-edbcdec51ba2",
    "monthly_price": 9.00
  },
  "languages": [
    "English",
    "עברית",
    "العربية",
    "ไทย",
    "Español",
    "Türkçe",
    "Français",
    "Deutsch",
    "Português",
    "Русский",
    "हिन्दी",
    "Filipino"
  ]
}
```

### **secrets.json** (LOCAL only, in .gitignore)
```json
{
  "telegram_token": "...",
  "claude_api_key": "...",
  "gemini_api_key": "...",
  "openai_api_key": "...",
  "lemonsqueezy_webhook_secret": "..."
}
```

---

## **Key Design Decisions**

### **1. Deep-Link Invitation System**
- **Problem**: Copy-paste codes are error-prone and poor UX
- **Solution**: Deep-links with one-tap share button
- Manager gets: `https://t.me/FarmTranslateBot?start=invite_BRIDGE-12345`
- Share button opens chat picker with prefilled invitation message
- Worker taps link → bot auto-extracts code → seamless connection
- **Benefits**: Zero typing, mobile-friendly, foolproof
- **5-digit codes**: BRIDGE-12345 (90,000 combinations vs 9,000 with 4 digits)

### **2. Industry-Specific Context**
- Manager selects industry during registration
- Industry context passed to all translations
- Same bot serves all industries (scalable SaaS model)
- Supported industries:
  - Dairy Farm
  - Farm / Agriculture
  - Construction
  - Restaurant
  - Warehouse
  - General Workplace

### **3. Configuration Split**
- **Problem**: Can't upload API keys to GitHub
- **Solution**: 
  - `config.json` = settings (safe to upload)
  - `secrets.json` = API keys (local only)
  - Environment variables = API keys (Railway)
- **Benefit**: Single `config.py` handles all sources

### **4. Provider Flexibility**
Different LLMs have different strengths:
- **Claude Sonnet 4**: Best overall quality, strong system prompts, industry context
- **Gemini Flash**: Schema enforcement prevents hallucinations, 40x cheaper
- **OpenAI GPT-4o**: Alternative option, structured outputs

**Switch providers by changing one line in config.json**

### **5. Conversation Context**
- Stores last N messages per conversation pair (configurable via `history_size`)
- Sliding window (default: 3 messages per side = 6 total)
- Helps with:
  - Pronouns ("she" = cow 115 from previous message)
  - Ambiguous words ("heat" in dairy = estrus/מיוחמת, not temperature/חום)
  - Topic continuity
- Stores original language (not translated) for better LLM understanding

### **6. Gender-Aware Translation**
- Asks gender during registration
- Passes to translation prompt
- Critical for Hebrew, Arabic, Spanish, French
- Example: "You need to check" → "אתה צריך" (male) vs "את צריכה" (female)

### **7. PostgreSQL with JSON Storage**
- Maintains same data structure as JSON files (KISS principle)
- Each row stores one user/conversation as JSONB
- Both bot and dashboard access same database
- Scalable to 50k+ users
- No file locking issues
- **4 tables**: users, conversations, usage_tracking, subscriptions

### **8. Normalized Conversation Keys**
- Key format: `"lowerID_higherID"` (always sorted)
- Manager ID: 9999, Worker ID: 1111 → Key: `"1111_9999"`
- Prevents duplication, enables easy lookup
- Works for one-to-one conversations

### **9. Media Forwarding**
- Non-text messages forwarded as-is (no translation)
- Supported media types:
  - Photos
  - Videos
  - Voice messages
  - Audio files
  - Documents/Files
  - Location
  - Contact
  - Stickers
- Adds sender context: "📎 From [Name]:"
- Preserves original media quality and metadata

### **10. Usage Tracking & Limits**
- Tracks by Telegram user ID (permanent, survives account resets)
- Only managers counted (workers send unlimited messages)
- Separate PostgreSQL table (`usage_tracking`)
- Configurable free limit (default: 50 messages)
- Can be enabled/disabled via `enforce_limits` config
- Dashboard shows usage stats and blocked status
- Admin can reset individual user limits
- **Anti-abuse**: User cannot bypass limit by resetting account
- **Subscription override**: If user is subscribed, usage tracking is skipped entirely

### **11. Payment Architecture - Lemon Squeezy Integration** ← NEW

**Why Lemon Squeezy?**
- Merchant of Record (handles VAT/tax globally)
- Simple webhook-based integration
- Customer portal (cancel/update payment without bot code)
- No PCI compliance needed
- Test mode works immediately (no approval needed)

**Architecture Pattern:**
```
Bot ← subscription_manager → PostgreSQL ← subscription_manager ← Webhook Handler
     (checks status)                                                (updates status)
```

**Separation of Concerns:**
- `subscription_manager.py` = Database CRUD only
- `dashboard.py` = Webhook processing + Telegram notifications
- `bot.py` = Subscription checking + Subscribe buttons
- **No duplication**: All services call subscription_manager for data access

**Checkout Flow:**
```
1. User hits limit
2. bot.py calls subscription_manager.create_checkout_url(telegram_id)
3. Returns: https://bridgeos.lemonsqueezy.com/checkout/buy/...?checkout[custom][telegram_id]=123456789
4. User completes payment on Lemon Squeezy
5. Lemon Squeezy sends webhook to dashboard.py
6. dashboard.py verifies signature → calls subscription_manager.save_subscription()
7. dashboard.py sends Telegram notification directly via Bot API
8. User receives: "✅ Subscription Active!"
```

**Subscription Lifecycle:**
- `subscription_created` → Status: active, unlimited messages
- `subscription_cancelled` → Status: cancelled, access until ends_at
- `subscription_expired` → Status: expired, back to free tier
- `subscription_payment_failed` → Status: paused, notify user
- `subscription_payment_recovered` → Status: active, notify user

**Security:**
- HMAC-SHA256 signature verification on all webhooks
- Webhook secret stored in environment variables
- No API keys in bot.py (only subscription checking)

**Customer Portal:**
- Managed entirely by Lemon Squeezy
- Accessible via `/subscription` command button
- Users can: cancel, update payment, view invoices, resume subscription

**Telegram Notifications:**
- Sent directly from dashboard.py via `requests.post()` to Telegram Bot API
- No dependency on bot.py (faster, independent)
- Events: created, cancelled, expired, payment_failed, resumed

### **12. Native Language Names** ← NEW
- Registration buttons show language names in native scripts
- Example: "עברית" instead of "Hebrew"
- User selects their own language → native names improve UX
- Maintains accessibility while being culturally appropriate

---

## **Data Models**

### **PostgreSQL Schema**

**users table:**
```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
)
```

**conversations table:**
```sql
CREATE TABLE conversations (
    conversation_key TEXT PRIMARY KEY,
    messages JSONB NOT NULL
)
```

**usage_tracking table:**
```sql
CREATE TABLE usage_tracking (
    telegram_user_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
)
```

**subscriptions table:** ← NEW
```sql
CREATE TABLE subscriptions (
    telegram_user_id TEXT PRIMARY KEY,
    data JSONB NOT NULL
)
```

### **User Data (in JSONB)**

**Manager:**
```json
{
  "language": "English",
  "gender": "Female",
  "role": "manager",
  "industry": "dairy_farm",
  "code": "BRIDGE-12345",
  "worker": "worker_id" or null
}
```

**Worker:**
```json
{
  "language": "Español",
  "gender": "Male",
  "role": "worker",
  "manager": "manager_id"
}
```

### **Conversation History (in JSONB)**
```json
[
  {
    "from": "user1",
    "text": "Check cow 115",
    "lang": "English",
    "timestamp": "2025-12-22T10:30:00"
  },
  {
    "from": "user2",
    "text": "היא נראית בריאה",
    "lang": "עברית",
    "timestamp": "2025-12-22T10:31:00"
  }
]
```

### **Usage Tracking Data (in JSONB)**
```json
{
  "messages_sent": 47,
  "blocked": false,
  "first_seen": "2025-12-22T10:30:00",
  "last_message": "2025-12-23T14:20:00"
}
```

### **Subscription Data (in JSONB)** ← NEW
```json
{
  "status": "active",
  "lemon_subscription_id": "1740398",
  "lemon_customer_id": "7417090",
  "started_at": "2025-12-22T21:09:39Z",
  "renews_at": "2026-01-22T21:09:37Z",
  "ends_at": null,
  "cancelled_at": null,
  "plan": "monthly",
  "customer_portal_url": "https://bridgeos.lemonsqueezy.com/billing/..."
}
```

**Subscription Status Values:**
- `active` - Paying subscriber, unlimited messages
- `cancelled` - Cancelled but still has access until ends_at
- `expired` - No access, back to free tier
- `paused` - Payment failed, blocked immediately
- `none` - No subscription record (free tier user)

---

## **Architecture**

### **System Architecture:**
```
┌────────────────────────────────┐
│      Lemon Squeezy             │
│   (Payment Processing)         │
└──────────┬─────────────────────┘
           │ Webhooks
           ↓
┌──────────────────────────────────────┐
│         PostgreSQL DB                │
│  ┌────────────────────────────────┐  │
│  │ users                          │  │
│  │ conversations                  │  │
│  │ usage_tracking                 │  │
│  │ subscriptions  ← NEW           │  │
│  └────────────────────────────────┘  │
└──────────┬───────────────────────────┘
           │
     ┌─────┴──────┐
     │            │
┌────▼─────┐  ┌──▼──────┐
│  Worker  │  │   Web   │
│  (bot)   │  │ (dash+  │
│          │  │webhooks)│
└──────────┘  └─────────┘
```

Both services share the same PostgreSQL database for real-time data access.

### **Payment Flow Architecture:**
```
User hits limit
     ↓
bot.py: Generate checkout URL with telegram_id
     ↓
User → Lemon Squeezy checkout → Completes payment
     ↓
Lemon Squeezy → Webhook → dashboard.py
     ↓
dashboard.py: Verify signature → Update PostgreSQL → Send Telegram notification
     ↓
User receives: "✅ Subscription Active!"
     ↓
Next message: bot.py checks subscription_manager.is_subscribed()
     ↓
Allowed (unlimited messages)
```

---

## **Commands**

### **Manager Commands:**
- `/start` - Register and get invitation link
- `/help` - Show available commands
- `/mycode` - Show invitation code and link
- `/subscription` - Manage subscription (view status, subscribe, portal link) ← NEW/UPDATED
- `/refer` - Recommend BridgeOS to other managers
- `/reset` - Delete account and start over

### **Worker Commands:**
- `/start invite_BRIDGE-12345` - Connect to manager via deep-link
- `/help` - Show available commands
- `/refer` - Recommend BridgeOS to other managers
- `/reset` - Delete account

### **Command Details:**

**`/subscription` (Managers only):** ← NEW/UPDATED

**Without subscription:**
```
📋 Subscription Status

Status: ❌ No Active Subscription
Messages Used: 35 / 50 (Free Tier)

💳 Subscribe to BridgeOS:
• Unlimited messages
• $9/month
• Cancel anytime

[💳 Subscribe ($9/month)]  ← Opens Lemon Squeezy checkout
```

**With active subscription:**
```
📋 Your Subscription

✅ Status: Active
💳 Plan: Unlimited Messages
💵 Price: $9/month
📅 Renews: 2026-01-23

Manage or cancel anytime.

[⚙️ Manage Subscription]  ← Opens Lemon Squeezy customer portal
```

**With cancelled subscription:**
```
📋 Your Subscription

⚠️ Status: Cancelled
💳 Plan: Unlimited Messages
💵 Price: $9/month
📅 Access Until: 2026-01-23

Manage or cancel anytime.

[⚙️ Manage Subscription]
```

---

## **Scaling Path**

### **Storage Scalability**

| Phase | Users | Storage | Action |
|-------|-------|---------|--------|
| MVP | < 500 | PostgreSQL with JSON | ✅ Current |
| Growth | 500-50,000 | PostgreSQL with JSON | No changes needed |
| Scale | > 50,000 | PostgreSQL with proper tables | Normalize schema |

### **Cost Optimization Path**

**Translation Costs (per 1,000 users, 500 msg/month each):**
- Claude Sonnet: ~$600/month
- Gemini Flash: ~$15/month

**Revenue (at 20% conversion to paid):**
- 200 subscribers × $9 = $1,800/month
- **Profit margin**: $1,800 - $15 (translation) - $20 (hosting) = $1,765/month

**Lemon Squeezy Fees:**
- 5% + $0.50 per transaction
- On $9 subscription: $0.95 fee = $8.05 net per subscriber
- Monthly with 200 subscribers: $1,610 net revenue

### **Deployment Evolution**

| Phase | Environment | Cost |
|-------|-------------|------|
| Development | Local machine | $0 |
| MVP | Railway (2 services + PostgreSQL) | $5-12/month |
| Production | Railway (scaled) | $20-50/month |
| Enterprise | Multi-region, load balanced | $100+/month |

---

## **Railway Deployment**

### **Services:**
1. **worker** - Runs `bot.py` (Telegram bot, background process)
2. **web** - Runs `dashboard.py` (Flask admin interface + webhook handler, public URL)
3. **PostgreSQL** - Shared database (automatically provided by Railway)

### **Environment Variables:**
- `TELEGRAM_TOKEN` - Bot token from @BotFather
- `CLAUDE_API_KEY` - Anthropic API key
- `GEMINI_API_KEY` - Google Gemini API key (optional)
- `OPENAI_API_KEY` - OpenAI API key (optional)
- `DATABASE_URL` - PostgreSQL connection (auto-set by Railway)
- `LEMONSQUEEZY_WEBHOOK_SECRET` - Webhook signing secret (from Lemon Squeezy) ← NEW

### **Webhook Configuration:**

**Railway Web Service URL:**
```
https://web-production-xxxxx.up.railway.app
```

**Lemon Squeezy Webhook Settings:**
- **Callback URL**: `https://web-production-xxxxx.up.railway.app/webhook/lemonsqueezy`
- **Signing Secret**: User-defined string (same as LEMONSQUEEZY_WEBHOOK_SECRET)
- **Events**: Select all `subscription_*` events (11 total)

**Important Notes:**
- Webhook handler is in `dashboard.py` (web service)
- Always returns 200 OK to prevent retry storms
- Verifies HMAC-SHA256 signature on every request
- Never use Lemon Squeezy API key as webhook secret (use signing secret)

### **Procfile:**
```
web: python dashboard.py
worker: python bot.py
```

---

## **Migration Strategies**

### **To Add LLM Provider:**
1. Add credentials to `secrets.json` (local) or Railway environment variables
2. Add model config to `config.json`
3. Add `translate_with_newprovider()` in `translator.py`
4. Update `translate()` routing logic
5. Change `translation_provider` in config

### **To Normalize PostgreSQL Schema (future):**
1. Create proper tables with foreign keys
2. Write migration script from JSONB to tables
3. Update `database.py`, `conversations.py`, `subscription_manager.py` internals
4. **No changes needed in bot.py or translator.py** ✅

### **To Add Payment Provider (future):**
1. Create new `payment_provider_manager.py` (copy subscription_manager.py pattern)
2. Update `config.json` with new provider settings
3. Update webhook handler in `dashboard.py`
4. Update checkout URL generation in bot.py
5. **Core logic stays the same** ✅

---

## **Current Status**

✅ **Completed:**
- Multi-language support (12 languages with native scripts)
- Gender-aware translation
- Industry-specific context (6 industries)
- Conversation history with sliding window
- Multiple LLM providers (Claude/Gemini/OpenAI)
- Clean config architecture (secrets separate)
- Cloud deployment (Railway, 24/7)
- Deep-link invitation system with share button
- 5-digit invitation codes (BRIDGE-12345)
- One-to-one manager-worker model
- Commands: `/start`, `/help`, `/mycode`, `/subscription`, `/refer`, `/reset`
- PostgreSQL database (scalable to 50k+ users)
- Real-time admin dashboard (monitoring & management)
- Media forwarding (photos, videos, voice, files, etc.)
- Usage tracking and message limits (50 free messages)
- Viral growth feature (`/refer` command)
- **Lemon Squeezy payment integration** ← NEW
- **Subscription management (/subscription command)** ← NEW
- **Webhook-based subscription lifecycle** ← NEW
- **Telegram notifications for subscription events** ← NEW
- **Customer portal for billing management** ← NEW
- **Freemium model (50 free → $9/month unlimited)** ← NEW

🔄 **In Progress:**
- Real user testing
- Cost monitoring
- Lemon Squeezy identity verification (test mode working)

📋 **Next Up:**
- Analytics dashboard (conversion tracking)
- Multi-worker support (v2)
- Voice message transcription + translation
- Mobile app (optional)

---

## **Technical Notes**

### **Python Version:**
- Local: 3.11.0
- Railway: 3.11.9 (specified in runtime.txt)

### **Dependencies:**
- python-telegram-bot==20.7
- anthropic (Claude API)
- google-generativeai (Gemini API)
- typing-extensions (for Gemini schemas)
- flask (Admin dashboard + webhook handler)
- psycopg2-binary (PostgreSQL driver)
- requests (for Telegram notifications from webhooks) ← NEW

### **Environment:**
- **Local**: Uses `secrets.json` for API keys
- **Railway**: Uses environment variables (TELEGRAM_TOKEN, CLAUDE_API_KEY, DATABASE_URL, LEMONSQUEEZY_WEBHOOK_SECRET, etc.)

### **Bot Link:**
https://t.me/FarmTranslateBot

### **Bot Configuration (@BotFather):**
- Description: Set via `/setdescription`
- About: Set via `/setabouttext`
- Commands: Set via `/setcommands`

---

## **Important Constraints**

1. **One worker per manager** (MVP only)
2. **Deep-link invitations** (modern UX with share button)
3. **5-digit codes** (BRIDGE-12345 format)
4. **Manager = anyone who registers without invite code**
5. **Worker = anyone who uses invite deep-link**
6. **Industry selected by manager**, worker inherits it
7. **Gender required** for translation accuracy in gendered languages
8. **PostgreSQL required** for shared data between bot and dashboard
9. **Message limits** - Only manager messages counted (when not subscribed), workers unlimited
10. **Usage tracking by Telegram ID** - Survives account resets (anti-abuse)
11. **Subscription checking** - Subscribed users bypass usage limits entirely ← NEW
12. **Payment via Lemon Squeezy** - Webhook-based, Merchant of Record ← NEW
13. **Customer portal for cancellation** - No cancel command needed ← NEW

---

## **Testing**

### **Local Development:**
1. Create `secrets.json` with API keys
2. Set `"enforce_limits": false` in `config.json` for testing
3. Run `python bot.py` and `python dashboard.py` separately
4. Use ngrok for webhook testing (optional)

### **Payment Testing:**
1. Lemon Squeezy test mode works during identity verification
2. Use test card: `4242 4242 4242 4242`
3. Test checkout URL: Add `?checkout[custom][telegram_id]=999888777`
4. Monitor Railway logs for webhook events
5. Check PostgreSQL `subscriptions` table
6. Verify Telegram notifications

### **Subscription Testing Checklist:**
- [ ] Free tier: Send 50 messages, see limit
- [ ] Subscribe button: Opens checkout with telegram_id
- [ ] Complete payment: Receive "Subscription Active" notification
- [ ] Send message: Unlimited, no counting
- [ ] /subscription: Shows active status with manage button
- [ ] Cancel: Keeps access until ends_at, receives notification
- [ ] Expiry: Returns to free tier, receives notification

See `docs/TESTING_GUIDE.md` for detailed procedures.

---

## **Security Considerations**

1. **API Keys**: Never commit to Git, use environment variables
2. **Webhook Signatures**: Always verify HMAC-SHA256 before processing
3. **Dashboard Password**: Change default password in production
4. **Database**: Railway PostgreSQL uses SSL by default
5. **Telegram Bot Token**: Keep secret, rotate if compromised
6. **Lemon Squeezy Webhook Secret**: Different from API key, keep separate

---

## **Monitoring & Analytics**

### **Dashboard Provides:**
- Total users (managers + workers)
- Active connections
- Total messages sent
- Subscription count
- Usage stats per manager
- Recent conversations

### **External Tools (Future):**
- Lemon Squeezy dashboard for revenue
- Sentry for error tracking
- PostHog for product analytics
- Railway metrics for performance

---

## **Support & Maintenance**

### **Common Issues:**

**"Subscription not working after payment"**
- Check Railway logs for webhook events
- Verify `LEMONSQUEEZY_WEBHOOK_SECRET` is set correctly
- Check PostgreSQL `subscriptions` table
- Test webhook signature verification

**"User still blocked after subscribing"**
- Check subscription status: `SELECT * FROM subscriptions WHERE telegram_user_id='123456789'`
- Verify `is_subscribed()` logic includes status check
- Check if subscription expired (ends_at passed)

**"Webhook not receiving events"**
- Verify Railway web service is running
- Check Lemon Squeezy webhook URL matches Railway domain
- Test webhook endpoint with curl
- Check Railway logs for incoming requests

### **Maintenance Tasks:**
- Monitor Railway database size (PostgreSQL)
- Review Lemon Squeezy failed payments
- Check subscription renewal rates
- Monitor translation costs vs revenue
- Update bot commands in @BotFather if changed

---

## **Future Enhancements**

### **Phase 2:**
- Multi-worker support (1 manager → N workers)
- Team plans (manager + 5 workers = $15/month)
- Annual subscriptions (discount)
- Analytics dashboard (conversion funnel)

### **Phase 3:**
- Voice message transcription + translation
- Video call integration (with live translation)
- Mobile app (native experience)
- Desktop app (for office computers)

### **Phase 4:**
- Multi-language group chats
- Translation quality feedback
- Custom industry vocabulary
- Integration with HR systems

---

**Last Updated**: December 23, 2025
**Version**: 2.0 (with Lemon Squeezy integration)