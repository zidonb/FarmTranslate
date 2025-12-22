# FarmTranslate - Architecture & Guidelines

---

## **What is FarmTranslate?**

FarmTranslate is a Telegram bot that enables real-time translated communication between managers and workers who speak different languages. Built initially for dairy farms with foreign workers, it now supports multiple industries through industry-specific translation contexts.

**Key Features:**
- One-to-one translated conversations (manager ↔ worker)
- Industry-specific terminology (dairy, construction, restaurant, warehouse, etc.)
- Gender-aware grammar for accurate translations in Hebrew, Arabic, Spanish, French
- Conversation history for contextual understanding
- Support for 10 languages
- Deep-link invitations with one-tap sharing
- Real-time admin dashboard

---

## **User Flow**

### **Manager Registration:**
```
1. /start
2. Select language (English, Hebrew, Arabic, Thai, Spanish, etc.)
3. Select gender (Male, Female, Prefer not to say)
4. Select industry (Dairy Farm, Construction, Restaurant, etc.)
5. Receives invitation with:
   - Code (e.g., FARM-1234)
   - Deep-link (https://t.me/FarmTranslateBot?start=invite_FARM-1234)
   - Share button (opens chat picker with prefilled message)
6. Taps share button → selects worker → sends invitation
```

### **Worker Registration:**
```
1. Receives invitation link from manager
2. Taps link → /start invite_FARM-1234 (code auto-extracted)
3. Select language
4. Select gender
5. ✅ Auto-connected! Can start chatting
```

### **Communication:**
```
Manager types: "Check cow 115 for heat"
   ↓
Bot retrieves conversation history from PostgreSQL
   ↓
Bot translates with industry context (dairy) + gender + history
   ↓
Worker receives: "בדוק את פרה 115 אם היא במחזור" (Hebrew, male form)
   ↓
Worker replies: "היא נראית בריאה"
   ↓
Manager receives: "She looks healthy"
```

---

## **Coding Principles**

1. **KISS** - Simple, readable code. No fancy abstractions.
2. **Minimal** - Only what we need for MVP. No "what if" features.
3. **Smart structure** - Clean separation so we can swap parts later:
   - Translation logic → separate module (easy to swap providers)
   - Database → PostgreSQL with JSON storage (scalable, shared data)
   - Bot handlers → clean functions (easy to add features)
   - Configuration → centralized, secrets separate

---

## **File Structure**
```
farm-translate/
├── bot.py                  # Main bot logic (handlers, commands, deep-link support)
├── translator.py           # Translation with multiple LLM providers
├── database.py             # PostgreSQL storage with clean interface
├── conversations.py        # Conversation history in PostgreSQL (sliding window)
├── dashboard.py            # Flask admin dashboard (real-time monitoring)
├── config.py               # Configuration loader (environment + files)
├── config.json             # Non-secret settings (safe to upload to GitHub)
├── secrets.json            # API keys (LOCAL only, in .gitignore)
├── requirements.txt        # Python dependencies
├── Procfile                # Railway deployment (web + worker services)
├── runtime.txt             # Python version (3.11.9)
├── .gitignore              # Exclude secrets and data files
└── docs/                   # Documentation folder
    ├── BACKGROUND.md       # Project context for new sessions
    ├── structure.md        # This file
    ├── POSTGRESQL_MIGRATION.md  # Database migration guide
    └── DASHBOARD_SETUP.md  # Dashboard setup instructions
```

---

## **Design Pattern: Separation of Concerns**

### **bot.py**
- Telegram bot handlers
- User registration flow (language → gender → industry OR auto-connect via deep-link)
- Deep-link support (`/start invite_FARM-1234`)
- InlineKeyboard share button with prefilled message
- Message routing logic
- Commands: `/start`, `/help`, `/mycode`, `/reset`
- No translation, database, or config logic

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
- Tables: `users` (user_id, data), conversations handled separately
- Shared access: Both bot and dashboard use same database

### **conversations.py**
- Conversation history management in PostgreSQL
- `get_conversation_history()` - Retrieve last N messages
- `add_to_conversation()` - Save message with sliding window
- `clear_conversation()` - Delete conversation history
- Pair-based keys: `"userID1_userID2"` (sorted, lowest first)
- Stores original language + text for better translation context
- Tables: `conversations` (conversation_key, messages)

### **dashboard.py**
- Flask web application for admin monitoring
- Real-time data from PostgreSQL (auto-refresh every 30s)
- Password protected (`farmadmin2024` - change this!)
- Features:
  - Statistics (total managers, workers, connections, messages)
  - Manager list with codes and connection status
  - Worker list with manager info
  - Recent conversations
  - Admin actions (delete users, clear conversations)
- See DASHBOARD_SETUP.md for details

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
  "history_size": 3,
  "languages": ["English", "Hebrew", "Arabic", ...]
}
```

### **secrets.json** (LOCAL only, in .gitignore)
```json
{
  "telegram_token": "...",
  "claude_api_key": "...",
  "gemini_api_key": "...",
  "openai_api_key": "..."
}
```

---

## **Key Design Decisions**

### **1. Deep-Link Invitation System**
- **Problem**: Copy-paste codes are error-prone and poor UX
- **Solution**: Deep-links with one-tap share button
- Manager gets: `https://t.me/FarmTranslateBot?start=invite_FARM-1234`
- Share button opens chat picker with prefilled invitation message
- Worker taps link → bot auto-extracts code → seamless connection
- **Benefits**: Zero typing, mobile-friendly, foolproof

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
- See POSTGRESQL_MIGRATION.md for migration guide

### **8. Normalized Conversation Keys**
- Key format: `"lowerID_higherID"` (always sorted)
- Manager ID: 9999, Worker ID: 1111 → Key: `"1111_9999"`
- Prevents duplication, enables easy lookup
- Works for one-to-one conversations

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

### **User Data (in JSONB)**

**Manager:**
```json
{
  "language": "English",
  "gender": "Female",
  "role": "manager",
  "industry": "dairy_farm",
  "code": "FARM-1234",
  "worker": "worker_id" or null
}
```

**Worker:**
```json
{
  "language": "Spanish",
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
    "lang": "Hebrew",
    "timestamp": "2025-12-22T10:31:00"
  }
]
```

---

## **Architecture**

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

Both services share the same PostgreSQL database for real-time data access.

---

## **Scaling Path**

### **Storage Scalability**

| Phase | Users | Storage | Action |
|-------|-------|---------|--------|
| MVP | < 500 | PostgreSQL with JSON | ✅ Current |
| Growth | 500-50,000 | PostgreSQL with JSON | No changes needed |
| Scale | > 50,000 | PostgreSQL with proper tables | Normalize schema |

### **Cost Optimization Path**

1. **Start**: Claude Sonnet 4 (~$0.0012 per message)
2. **Test**: Gemini Flash 2.0 (40x cheaper, ~$0.00003 per message)
3. **Optimize**: Reduce context size if needed
4. **Scale**: Use cheaper models for simple messages, Claude for complex

**Cost Estimates (at 1,000 users, 500 msg/month each):**
- Claude Sonnet: ~$600/month
- Gemini Flash: ~$15/month

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
2. **web** - Runs `dashboard.py` (Flask admin interface, public URL)
3. **PostgreSQL** - Shared database (automatically provided by Railway)

### **Environment Variables:**
- `TELEGRAM_TOKEN` - Bot token from @BotFather
- `CLAUDE_API_KEY` - Anthropic API key
- `GEMINI_API_KEY` - Google Gemini API key (optional)
- `OPENAI_API_KEY` - OpenAI API key (optional)
- `DATABASE_URL` - PostgreSQL connection (auto-set by Railway)

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
3. Update `database.py` and `conversations.py` internals
4. **No changes needed in bot.py or translator.py** ✅

---

## **Current Status**

✅ **Completed:**
- Multi-language support (10 languages)
- Gender-aware translation
- Industry-specific context (6 industries)
- Conversation history with sliding window
- Multiple LLM providers (Claude/Gemini/OpenAI)
- Clean config architecture (secrets separate)
- Cloud deployment (Railway, 24/7)
- Deep-link invitation system with share button
- One-to-one manager-worker model
- Commands: `/start`, `/help`, `/mycode`, `/reset`
- PostgreSQL database (scalable to 50k+ users)
- Real-time admin dashboard (monitoring & management)

🔄 **In Progress:**
- Real user testing
- Cost monitoring

📋 **Next Up:**
- Multi-worker support (v2)
- Analytics dashboard
- Payment integration (Telegram Payments)
- Voice message support

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
- flask (Admin dashboard)
- psycopg2-binary (PostgreSQL driver)

### **Environment:**
- **Local**: Uses `secrets.json` for API keys
- **Railway**: Uses environment variables (TELEGRAM_TOKEN, CLAUDE_API_KEY, DATABASE_URL, etc.)

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
3. **Manager = anyone who registers without invite code**
4. **Worker = anyone who uses invite deep-link**
5. **Industry selected by manager**, worker inherits it
6. **Gender required** for translation accuracy in gendered languages
7. **PostgreSQL required** for shared data between bot and dashboard