# BridgeOS - Architecture & Guidelines

---

## **What is BridgeOS?**

BridgeOS (formerly FarmTranslate) is a Telegram bot that enables real-time translated communication between managers and workers who speak different languages. Built initially for dairy farms with foreign workers, it now supports multiple industries through industry-specific translation contexts.

BridgeOS is an AI-powered Operating System designed to manage foreign workforces by transforming simple translation into operational control. It functions as a command center that not only translates communication in real-time but also automatically generates daily action items, tracks task completion with "closed-loop" accountability, and converts unstructured worker reports into organized data logs. By bridging the gap between instruction and execution, BridgeOS ensures that nothing—from safety hazards to critical tasks—gets lost in translation.

**Key Features:**
- One-to-one translated conversations (manager ↔ worker)
- Industry-specific terminology (dairy, construction, restaurant, warehouse, etc.)
- Gender-aware grammar for accurate translations in Hebrew, Arabic, Spanish, French
- Conversation history for contextual understanding
- Support for 12 languages (including native scripts)
- Deep-link invitations with one-tap sharing
- **Real-time admin dashboard with 2-page manager detail views** ✅ COMPLETE
- Media forwarding (photos, videos, voice messages, files)
- **AI-powered daily action items** - Extract tasks from conversations ✅
- **Subscription management with Lemon Squeezy** ✅
- **Usage tracking with free tier (8 messages) + unlimited paid tier** ✅
- Telegram notifications for subscription events

---

## **Business Model**

### **Freemium + Subscription:**
- **Free Tier**: 8 messages per manager (testing mode)
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
Bot retrieves last 6 messages from translation_msg_context (for translation)
   ↓
Bot translates with industry context (dairy) + gender + history
   ↓
Worker receives: "בדוק את פרה 115 אם היא במחזור" (Hebrew, male form)
   ↓
Bot saves message to BOTH:
   - translation_msg_context (last 6 messages for translation)
   - message_history (full 30-day history for action items)
   ↓
Bot increments manager's message counter (if not subscribed)
   ↓
Worker replies: "היא נראית בריאה"
   ↓
Manager receives: "She looks healthy"
```

### **Daily Action Items Flow:**
```
Manager types: /daily
   ↓
Bot checks: Is user a manager? (workers don't get action items)
   ↓
Bot retrieves last 24 hours of messages from message_history
   ↓
Bot sends messages to Claude with prompt:
   "Extract action items only (tasks, safety issues, equipment problems)"
   Output ONLY in manager's language
   ↓
Claude returns bullet-list action items (in manager's language)
   ↓
Manager receives:
   "📋 Daily Action Items (Last 24 Hours)
   
   Action Items:
   • Check cow 115 for heat
   • Fix broken gate in section 3
   • Order more feed by Friday
   
   Safety Issues:
   • Electrical panel sparking - needs attention
   
   Total messages: 47"
```

### **Subscription Journey:**
```
Manager sends 8th message
   ↓
Bot shows: "⚠️ You've reached the free limit (8 messages)"
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
On expiry: Receives notification, returns to free tier (8 messages)
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
   - **Message storage** → Two separate tables (translation context vs full history)
   - **Dashboard** → Two-page design (overview + detail pages) ✅

---

## **File Structure**
```
bridgeos/
├── bot.py                          # Main bot logic (handlers, commands, deep-link support)
├── translator.py                   # Translation with multiple LLM providers + action items
├── database.py                     # PostgreSQL storage with clean interface
├── translation_msg_context.py      # Last 6 messages for translation context
├── message_history.py              # Full 30-day history for action items
├── usage_tracker.py                # Message limit tracking and enforcement
├── subscription_manager.py         # Subscription CRUD operations (database interface)
├── dashboard.py                    # Flask admin dashboard + Lemon Squeezy webhooks ✅ COMPLETE
├── config.py                       # Configuration loader (environment + files)
├── config.json                     # Non-secret settings (safe to upload to GitHub)
├── secrets.json                    # API keys (LOCAL only, in .gitignore)
├── requirements.txt                # Python dependencies
├── Procfile                        # Railway deployment (web + worker services)
├── runtime.txt                     # Python version (3.11.9)
├── .gitignore                      # Exclude secrets and data files
└── docs/                           # Documentation folder
    ├── BACKGROUND.md               # Project context for new sessions
    ├── structure.md                # This file ✅ UPDATED
    ├── POSTGRESQL_MIGRATION.md     # Database migration guide
    ├── DASHBOARD_SETUP.md          # Dashboard setup instructions
    ├── DEPLOYMENT_CHECKLIST.md     # Lemon Squeezy deployment guide
    └── TESTING_GUIDE.md            # Payment testing procedures
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
- Subscription checking before sending messages
- Subscribe button generation with Lemon Squeezy checkout URL
- Usage limit enforcement (checks before sending, increments after)
- Daily action items generation (`/daily` command)
- Commands: `/start`, `/help`, `/mycode`, `/subscription`, `/daily`, `/refer`, `/reset`
- No translation, database, payment, or config logic

### **translator.py**
- Provider-agnostic `translate()` function
- Accepts conversation history and industry for context
- Provider-specific implementations:
  - `translate_with_claude()` - Strong system prompt with industry context
  - `translate_with_gemini()` - Schema-enforced JSON (prevents answering questions)
  - `translate_with_openai()` - System prompt approach
- `build_translation_prompt()` - Handles context, gender, industry
- `generate_daily_actionitems()` - Uses Claude for extracting action items in manager's language

### **database.py**
- Simple function interface: `get_user()`, `save_user()`, `get_all_users()`
- PostgreSQL with JSONB storage (maintains same data structure as JSON files)
- Tables: `users`, `translation_msg_context`, `message_history`, `usage_tracking`, `subscriptions`
- Shared access: Both bot and dashboard use same database

### **translation_msg_context.py**
- Translation context management in PostgreSQL
- `get_conversation_history()` - Retrieve last N messages (default: 6)
- `add_to_conversation()` - Save message with sliding window
- `clear_conversation()` - Delete conversation history
- Pair-based keys: `"userID1_userID2"` (sorted, lowest first)
- Stores original language + text for better translation context
- **Sliding window** - Only keeps last 6 messages (configurable via `translation_context_size`)
- Tables: `translation_msg_context` (conversation_key, messages)

### **message_history.py**
- **Full conversation history** for action items and analytics
- `save_message()` - Save message with timestamp + auto-cleanup
- `get_messages()` - Retrieve messages with optional time filter (e.g., last 24 hours)
- `cleanup_old_messages()` - Auto-delete messages older than retention period
- `get_message_count()` - Count messages in timeframe
- `clear_history()` - Admin function to delete all messages
- `get_all_conversations()` - For dashboard monitoring
- **Automatic cleanup** - Runs on every message save (configurable retention period)
- **30-day retention** - Configurable via `message_retention_days` in config.json
- Tables: `message_history` (conversation_key, messages)
- **Separation principle**: Translation context and full history are separate

### **usage_tracker.py**
- Message limit tracking and enforcement
- Tracks by Telegram user ID (survives account resets)
- Functions:
  - `get_usage()` - Get usage data for a user
  - `is_user_blocked()` - Check if user has reached limit (respects testing mode whitelist)
  - `increment_message_count()` - Count message and check limit
  - `reset_user_usage()` - Admin function to reset limits
  - `get_usage_stats()` - Aggregated statistics
- Tables: `usage_tracking` (telegram_user_id, data)
- Only tracks manager messages when not subscribed (workers unlimited)
- Configurable limit (default: 8 free messages in testing mode)
- **Testing mode whitelist** - Specific user IDs bypass limits for testing

### **subscription_manager.py**
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

### **dashboard.py** ✅ COMPLETE
- Flask web application for admin monitoring
- **Lemon Squeezy webhook handler** (`/webhook/lemonsqueezy`)
- Real-time data from PostgreSQL
- Password protected (`zb280072A` - change this!)
- **Two-page design**: ✅ IMPLEMENTED
  - **Page 1: Overview (/)** - Stats + manager/worker/subscription tables
  - **Page 2: Manager Details (/manager/{id})** - Comprehensive manager view ✅ COMPLETE
- **Manager Detail Page Features**: ✅ COMPLETE
  - **Clean Header Layout**: Title + ID on left, navigation buttons stacked on right
  - **Section 1**: Manager info (ID, code, language, gender, industry)
  - **Section 2**: Connection & subscription (worker details, subscription status, portal link)
  - **Section 3**: Translation context (last 6 messages, always visible)
  - **Section 4**: Full message history (collapsible, 30 days, filter buttons)
  - **Section 5**: Admin actions (reset usage, clear contexts, delete account)
- **Routes**:
  - `/` - Main dashboard (overview)
  - `/manager/<user_id>` - Manager detail page ✅ COMPLETE
  - `/clear_translation_context/<user_id>` - Clear last 6 messages ✅ COMPLETE
  - `/clear_full_history/<user_id>` - Clear 30-day history ✅ COMPLETE
  - `/delete_user/<user_id>` - Delete manager/worker
  - `/reset_usage/<user_id>` - Reset message limits
  - `/webhook/lemonsqueezy` - Payment webhook handler
  - `/login` - Password authentication
  - `/logout` - Session termination
- **Webhook Processing**:
  - Verifies HMAC-SHA256 signature
  - Processes 11 subscription event types
  - Updates PostgreSQL via subscription_manager
  - Sends Telegram notifications via Bot API
  - Always returns 200 OK (prevents retry storms)
- **Scalability**: Overview stays fast (no message loading), details load on-demand
- **Responsive Design**: Works on desktop, tablet, and mobile

### **config.py**
- Single source of truth for configuration
- Reads from:
  - `config.json` (non-secret settings)
  - `secrets.json` (local development)
  - Environment variables (Railway deployment)
- All other files import: `from config import load_config`

### **config.json** (Safe to upload)
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
  "translation_context_size": 3,
  "message_retention_days": 30,
  "free_message_limit": 8,
  "enforce_limits": true,
  "testing_mode": true,
  "test_user_ids": ["6425887398"],
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
  ],
  "claude": {
    "model": "claude-sonnet-4-20250514"
  }
}
```

**Config Options:**
- `translation_context_size: 3` - Messages per side for translation (6 total)
- `message_retention_days: 30` - How long to keep full message history
- `free_message_limit: 8` - Free tier limit (testing mode)
- `testing_mode: true` - Enable testing features
- `test_user_ids: ["6425887398"]` - Whitelist for unlimited messages during testing

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
  - Nursing & Elderly Care
  - Hospitality / Hotels
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
- **Claude Sonnet 4**: Best overall quality, strong system prompts, industry context, action items generation
- **Gemini Flash**: Schema enforcement prevents hallucinations, 40x cheaper
- **OpenAI GPT-4o**: Alternative option, structured outputs

**Switch providers by changing one line in config.json**

### **5. Conversation Context**
- Stores last N messages per conversation pair (configurable via `translation_context_size`)
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
- **5 tables**: users, translation_msg_context, message_history, usage_tracking, subscriptions

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
- Configurable free limit (default: 8 messages in testing mode)
- Can be enabled/disabled via `enforce_limits` config
- Dashboard shows usage stats and blocked status
- Admin can reset individual user limits
- **Anti-abuse**: User cannot bypass limit by resetting account
- **Subscription override**: If user is subscribed, usage tracking is skipped entirely
- **Testing mode whitelist**: Specific user IDs bypass limits for testing

### **11. Payment Architecture - Lemon Squeezy Integration**

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

### **12. Native Language Names**
- Registration buttons show language names in native scripts
- Example: "עברית" instead of "Hebrew"
- User selects their own language → native names improve UX
- Maintains accessibility while being culturally appropriate

### **13. Dual Storage Architecture**

**Problem**: Translation needs last 6 messages (fast), action items need 30 days (comprehensive)

**Solution**: Two separate PostgreSQL tables with different purposes

**Table 1: `translation_msg_context`**
- **Purpose**: Fast translation with recent context
- **Storage**: Last 6 messages only (sliding window)
- **Retention**: Automatic (keeps newest 6)
- **Use case**: Real-time translation
- **Performance**: Minimal data, fast queries

**Table 2: `message_history`**
- **Purpose**: Full conversation history for action items and analytics
- **Storage**: All messages for 30 days
- **Retention**: Automatic cleanup (deletes messages >30 days on every save)
- **Use case**: Daily action items, analytics, auditing
- **Performance**: Larger data, time-based filtering

**Benefits:**
- ✅ **Separation of concerns** - Translation and action items don't conflict
- ✅ **Performance** - Translation queries stay fast (6 messages vs thousands)
- ✅ **Data duplication** - Last 6 messages exist in both tables (acceptable trade-off)
- ✅ **Independent optimization** - Can tune each table separately
- ✅ **Automatic cleanup** - No manual maintenance, runs on every message save

**Cost:**
- Storage: ~$0.06/month for 1000 users (negligible)
- Maintenance: Zero (automatic cleanup)

### **14. On-Demand Daily Action Items**

**Why on-demand vs auto-scheduled?**
- ✅ Validates demand (are users actually using it?)
- ✅ Cost control (only generate when requested)
- ✅ Better UX (manager decides when they need it)
- ✅ Simpler implementation (no cron jobs)

**Command Name: `/daily`**
- Short and memorable (6 characters)
- Natural ("I want my daily report")
- Scalable for future `/weekly`, `/monthly`

**Scope:**
- **Timeframe**: Last 24 hours (not calendar day - avoids timezone complexity)
- **Content**: Action items ONLY (tasks, safety issues, equipment problems)
- **Format**: Bullet list with • symbol (easy to scan)
- **Language**: Manager's language (CRITICAL - must match manager's registered language)
- **Provider**: Claude Sonnet 4 (best quality for extraction)

**Anti-Summarization Strategy:**
- Explicit prompt instruction: "Do NOT summarize. ONLY extract action items."
- Clear INCLUDE/EXCLUDE sections
- Specificity requirement: "include names, numbers, locations"
- Format specification: Shows exact bullet format
- Language mandate: "Your ENTIRE response must be in {manager_language}"

**Cost Optimization:**
- Use full message history (not just last N messages)
- Filter by timestamp (last 24 hours)
- Extract action items only (skip greetings, confirmations)

### **15. Dashboard Scalability** ✅ IMPLEMENTED

**Problem**: Showing ALL conversations for ALL managers doesn't scale

**Solution**: Two-page hybrid approach ✅ COMPLETE

**Page 1: Dashboard Overview (/)**
- Stats cards (managers, workers, connections, messages, subscriptions)
- Managers table with **👁️ View Details** button ✅
- Workers table
- Subscriptions table
- Recent conversations (last 10 messages from translation context)
- **Performance**: Fast (no message_history loading)

**Page 2: Manager Detail Page (/manager/{id})** ✅ NEW
- **Header Layout** (Flexbox design): ✅ COMPLETE
  - Left: 👤 Manager Details + Manager ID underneath
  - Right: ← Back to Dashboard + 🚪 Logout (stacked vertically)
  - Clean, professional, no overlapping elements
- **Section 1**: Manager info (ID, code, language, gender, industry)
- **Section 2**: Connection & subscription (worker info, subscription status, portal link)
- **Section 3**: Translation context (last 6 messages, always visible, color-coded)
- **Section 4**: Full message history (collapsible/expandable, 30 days, filter buttons)
- **Section 5**: Admin actions (reset usage, clear contexts, delete account)

**Benefits:**
- ✅ Scalability - Overview stays fast, details load on-demand
- ✅ Privacy - Only load conversations when needed
- ✅ Usability - Natural click-through workflow
- ✅ Debugging - Easy to help specific managers
- ✅ Context - See everything about one manager in one place
- ✅ Professional UI - Clean header layout, no overlapping elements

**Implementation Status**: ✅ COMPLETE (December 28, 2025)

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

**translation_msg_context table:**
```sql
CREATE TABLE translation_msg_context (
    conversation_key TEXT PRIMARY KEY,
    messages JSONB NOT NULL
)
```

**message_history table:**
```sql
CREATE TABLE message_history (
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

**subscriptions table:**
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

### **Translation Context (in JSONB)**
```json
[
  {
    "from": "user1",
    "text": "Check cow 115",
    "lang": "English",
    "timestamp": "2025-12-26T10:30:00+00:00"
  },
  {
    "from": "user2",
    "text": "היא נראית בריאה",
    "lang": "עברית",
    "timestamp": "2025-12-26T10:31:00+00:00"
  }
]
```
**Note**: Only last 6 messages (sliding window)

### **Message History (in JSONB)**
```json
[
  {
    "from": "user1",
    "text": "Check cow 115",
    "lang": "English",
    "timestamp": "2025-12-26T10:30:00+00:00"
  },
  {
    "from": "user2",
    "text": "היא נראית בריאה",
    "lang": "עברית",
    "timestamp": "2025-12-26T10:31:00+00:00"
  },
  ...
  (all messages for last 30 days)
]
```
**Note**: Full history, auto-cleanup removes messages >30 days old

### **Usage Tracking Data (in JSONB)**
```json
{
  "messages_sent": 5,
  "blocked": false,
  "first_seen": "2025-12-25T10:30:00",
  "last_message": "2025-12-26T14:20:00"
}
```

### **Subscription Data (in JSONB)**
```json
{
  "status": "active",
  "lemon_subscription_id": "1740398",
  "lemon_customer_id": "7417090",
  "started_at": "2025-12-25T21:09:39Z",
  "renews_at": "2026-01-25T21:09:37Z",
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
│  │ translation_msg_context        │  │
│  │ message_history                │  │
│  │ usage_tracking                 │  │
│  │ subscriptions                  │  │
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

### **Message Flow Architecture:**
```
User sends message
     ↓
bot.py saves to TWO tables:
     ├─→ translation_msg_context (last 6 messages, sliding window)
     └─→ message_history (full 30 days, auto-cleanup)
     ↓
Translation uses: translation_msg_context (fast, 6 messages)
     ↓
Daily action items use: message_history (comprehensive, 24 hours filtered)
```

### **Dashboard Architecture:** ✅ COMPLETE
```
Main Dashboard (/)
     ↓
Manager clicks [👁️ View Details]
     ↓
Manager Detail Page (/manager/{id})
     ├─→ Header: Title (left) + Navigation (right, stacked)
     ├─→ Section 1: Manager Info
     ├─→ Section 2: Connection & Subscription
     ├─→ Section 3: Translation Context (6 messages)
     ├─→ Section 4: Full History (30 days, collapsible)
     └─→ Section 5: Admin Actions
```

---

## **Commands**

### **Manager Commands:**
- `/start` - Register and get invitation link
- `/help` - Show available commands
- `/mycode` - Show invitation code and link
- `/subscription` - Manage subscription (view status, subscribe, portal link)
- `/daily` - Get daily action items (last 24 hours)
- `/refer` - Recommend BridgeOS to other managers
- `/reset` - Delete account and start over

### **Worker Commands:**
- `/start invite_BRIDGE-12345` - Connect to manager via deep-link
- `/help` - Show available commands
- `/refer` - Recommend BridgeOS to other managers
- `/reset` - Delete account

### **Command Details:**

**`/subscription` (Managers only):**

**Without subscription:**
```
📋 Subscription Status

Status: ❌ No Active Subscription
Messages Used: 5 / 8 (Free Tier)

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
📅 Renews: 2026-01-26

Manage or cancel anytime.

[⚙️ Manage Subscription]  ← Opens Lemon Squeezy customer portal
```

**With cancelled subscription:**
```
📋 Your Subscription

⚠️ Status: Cancelled
💳 Plan: Unlimited Messages
💵 Price: $9/month
📅 Access Until: 2026-01-26

Manage or cancel anytime.

[⚙️ Manage Subscription]
```

**`/daily` (Managers only):**

**When messages exist:**
```
📋 Daily Action Items (Last 24 Hours)

Action Items:
• Check cow 115 for heat
• Fix broken gate in section 3
• Order more feed by Friday

⚠️ Safety Issues:
• Electrical panel sparking - needs immediate attention

🔧 Equipment:
• Milking machine #2 making noise

Total messages: 47
```

**When no messages:**
```
📋 Daily Action Items (Last 24 Hours)

No messages found in the last 24 hours.

Start a conversation with your worker to see action items here!
```

**When no action items:**
```
📋 Daily Action Items (Last 24 Hours)

No action items found.

Your team is all caught up! ✅

Total messages: 12
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

**Daily Action Items Costs (per 1,000 users, 1 request/day):**
- Claude Sonnet: ~$15/month (30 requests × $0.0005 per request)
- Negligible compared to translation costs

**Revenue (at 20% conversion to paid):**
- 200 subscribers × $9 = $1,800/month
- **Profit margin**: $1,800 - $15 (translation) - $15 (action items) - $20 (hosting) = $1,750/month

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
- `LEMONSQUEEZY_WEBHOOK_SECRET` - Webhook signing secret (from Lemon Squeezy)

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
3. Update `database.py`, `translation_msg_context.py`, `message_history.py`, `subscription_manager.py` internals
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
- Industry-specific context (8 industries)
- Conversation history with sliding window
- Multiple LLM providers (Claude/Gemini/OpenAI)
- Clean config architecture (secrets separate)
- Cloud deployment (Railway, 24/7)
- Deep-link invitation system with share button
- 5-digit invitation codes (BRIDGE-12345)
- One-to-one manager-worker model
- Commands: `/start`, `/help`, `/mycode`, `/subscription`, `/daily`, `/refer`, `/reset`
- PostgreSQL database (scalable to 50k+ users)
- Real-time admin dashboard (monitoring & management)
- Media forwarding (photos, videos, voice, files, etc.)
- Usage tracking and message limits (8 free messages in testing)
- Viral growth feature (`/refer` command)
- Lemon Squeezy payment integration
- Subscription management (`/subscription` command)
- Webhook-based subscription lifecycle
- Telegram notifications for subscription events
- Customer portal for billing management
- Freemium model (8 free → $9/month unlimited in testing)
- **Dual storage architecture** (translation context + full history)
- **`/daily` command** (AI-powered action items extraction)
- **Manager language support** (action items in manager's language)
- **Anti-summarization prompt** (ensures bullet points, not summaries)
- **Testing mode whitelist** (unlimited messages for test users)
- **Dashboard redesign** (2-page manager detail view) ✅ COMPLETE
- **Professional header layout** (clean, no overlapping elements) ✅ COMPLETE

📋 **Ready for Production:**
- Dashboard fully functional and tested
- All routes operational
- Admin actions working
- Responsive design verified

🔄 **Future Enhancements:**
- Functional filter buttons (24h, 7d, 30d) - Currently placeholders
- Pagination for large histories (>100 messages)
- Search functionality on main dashboard
- Task tracking with checkboxes (Telegram InlineKeyboard)
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
- requests (for Telegram notifications from webhooks)

### **Environment:**
- **Local**: Uses `secrets.json` for API keys
- **Railway**: Uses environment variables (TELEGRAM_TOKEN, CLAUDE_API_KEY, DATABASE_URL, LEMONSQUEEZY_WEBHOOK_SECRET, etc.)

### **Bot Link:**
https://t.me/FarmTranslateBot

### **Bot Configuration (@BotFather):**
- Description: Set via `/setdescription`
- About: Set via `/setabouttext`
- Commands: Set via `/setcommands` (includes `/daily`)

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
11. **Subscription checking** - Subscribed users bypass usage limits entirely
12. **Payment via Lemon Squeezy** - Webhook-based, Merchant of Record
13. **Customer portal for cancellation** - No cancel command needed
14. **Dual storage** - Translation context (6 messages) + Full history (30 days)
15. **Action items for managers only** - Workers don't get `/daily` command
16. **Manager language output** - Action items MUST be in manager's registered language
17. **Testing mode** - Specific users bypass limits for development
18. **Dashboard scalability** - Two-page design (overview + detail) ✅

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

### **Daily Action Items Testing:**
1. Send multiple messages between manager and worker
2. Manager types `/daily`
3. Check if action items are extracted correctly (not summarized)
4. Verify output is in manager's language
5. Test with no messages (last 24 hours)
6. Test with messages but no action items
7. Verify format (bullets with • symbol)

### **Dashboard Testing:** ✅ COMPLETE
1. Login to dashboard (password: `zb280072A`)
2. Verify stats cards display correctly
3. Click "👁️ View Details" on a manager
4. Verify all 5 sections load:
   - Manager info
   - Connection & subscription
   - Translation context (6 messages)
   - Full history (collapsible)
   - Admin actions
5. Test collapsible functionality (click header)
6. Test admin actions (clear context, clear history)
7. Test on mobile (responsive design)
8. Verify header layout (no overlapping elements)
9. Test navigation (back button, logout button)

### **Subscription Testing Checklist:**
- [ ] Free tier: Send 8 messages, see limit
- [ ] Subscribe button: Opens checkout with telegram_id
- [ ] Complete payment: Receive "Subscription Active" notification
- [ ] Send message: Unlimited, no counting
- [ ] `/subscription`: Shows active status with manage button
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
- **Manager detail pages** with full conversation history ✅

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

**"Action items showing old messages"**
- Check `message_retention_days` in config.json
- Verify cleanup is running (check logs for "Cleaned up X old messages")
- Query PostgreSQL: `SELECT * FROM message_history WHERE conversation_key='...'`

**"Action items not extracting properly"**
- Check Claude API response in logs
- Verify prompt includes industry context AND manager language
- Test with different message content
- Check if messages exist in last 24 hours

**"Action items in wrong language"**
- Verify manager's language in database: `SELECT data FROM users WHERE user_id='...'`
- Check translator.py receives `manager_language` parameter
- Test prompt with explicit language instruction

**"Dashboard manager detail page not loading"**
- Check if manager ID exists in database
- Verify `/manager/<user_id>` route is accessible
- Check Railway logs for Python errors
- Verify message_history import in dashboard.py

**"Translation context empty on detail page"**
- Check if manager has worker connected
- Verify messages exist in translation_msg_context table
- Query: `SELECT * FROM translation_msg_context WHERE conversation_key='...'`

**"Full history not displaying"**
- Check if messages exist in message_history table
- Verify collapsible section is expanding (JavaScript)
- Check for JavaScript console errors
- Test with different browsers

**"Header elements overlapping"** ✅ FIXED
- Verify flexbox CSS is applied to `.header`
- Check `.header-left` and `.header-right` wrapper divs exist
- Ensure back button and logout button are in `.header-right`

### **Maintenance Tasks:**
- Monitor Railway database size (PostgreSQL)
- Review Lemon Squeezy failed payments
- Check subscription renewal rates
- Monitor translation costs vs revenue
- Update bot commands in @BotFather if changed
- **Monitor message history retention** - Verify auto-cleanup is working
- **Test action items quality** - Ensure no summarization creep
- **Test dashboard on mobile** - Verify responsive design ✅
- **Monitor dashboard performance** - Check page load times ✅

---

## **Future Enhancements**

### **Phase 2:**
- **Functional filter buttons** - Make 24h, 7d, 30d filters work (currently placeholders)
- **Pagination** - Add page numbers for large histories (20 per page)
- **Search on main dashboard** - Filter managers by name, code, language
- **Task tracking with checkboxes** (Telegram InlineKeyboard)
  - Parse action items from `/daily` response
  - Add "✅ Done" buttons for workers
  - Track completion status
  - Notify manager when completed
- Multi-worker support (1 manager → N workers)
- Team plans (manager + 5 workers = $15/month)
- Annual subscriptions (discount)
- Analytics dashboard (conversion funnel)

### **Phase 3:**
- Voice message transcription + translation
- Video call integration (with live translation)
- Mobile app (native experience)
- Desktop app (for office computers)
- **Auto-scheduled action items** (premium feature)
- **Export conversations** (CSV/JSON)
- **Activity timeline** on dashboard
- **Bulk admin actions** (reset all blocked users)

### **Phase 4:**
- Multi-language group chats
- Translation quality feedback
- Custom industry vocabulary
- Integration with HR systems
- **Advanced analytics** (task completion rates, response times)
- **Real-time dashboard updates** (WebSocket)

---

**Last Updated**: December 28, 2025
**Version**: 3.2 (Dashboard redesign complete with improved header layout, ready for production)