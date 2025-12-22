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

---

## **User Flow**

### **Manager Registration:**
```
1. /start
2. Select language (English, Hebrew, Arabic, Thai, Spanish, etc.)
3. Select gender (Male, Female, Prefer not to say)
4. Choose: "Registering" or "Invited"
   → Selects "Registering"
5. Select industry (Dairy Farm, Construction, Restaurant, etc.)
6. Receives invitation code (e.g., FARM-1234) + bot link
7. Shares code with worker
```

### **Worker Registration:**
```
1. /start
2. Select language
3. Select gender
4. Choose: "Registering" or "Invited"
   → Selects "Invited"
5. Enter manager's code (FARM-1234)
6. Connected! Can start chatting
```

### **Communication:**
```
Manager types: "Check cow 115 for heat"
   ↓
Bot retrieves conversation history
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
   - Database → simple interface (easy to upgrade to PostgreSQL)
   - Bot handlers → clean functions (easy to add features)
   - Configuration → centralized, secrets separate

---

## **File Structure**
```
farm-translate/
├── bot.py                  # Main bot logic (handlers, commands, conversation flow)
├── translator.py           # Translation with multiple LLM providers
├── database.py             # JSON storage with clean interface
├── conversations.py        # Conversation history management (sliding window)
├── config.py               # Configuration loader (environment + files)
├── config.json             # Non-secret settings (safe to upload to GitHub)
├── secrets.json            # API keys (LOCAL only, in .gitignore)
├── users.json              # User data (auto-created)
├── conversations.json      # Conversation history (auto-created)
├── requirements.txt        # Python dependencies
├── Procfile                # Railway deployment config
├── runtime.txt             # Python version (3.11.9)
├── .gitignore              # Exclude secrets and data files
└── docs/                   # Documentation folder
    ├── BACKGROUND.md       # Project context for new sessions
    ├── structure.md        # This file
    └── todo.md             # Development roadmap
```

---

## **Design Pattern: Separation of Concerns**

### **bot.py**
- Telegram bot handlers
- User registration flow (language → gender → registering/invited → industry/code)
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
- Currently: JSON file storage
- Future: Swap to PostgreSQL without changing caller code

### **conversations.py**
- Conversation history management
- `get_conversation_history()` - Retrieve last N messages
- `add_to_conversation()` - Save message with sliding window
- `clear_conversation()` - Delete conversation history
- Pair-based keys: `"userID1_userID2"` (sorted, lowest first)
- Stores original language + text for better translation context

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

### **1. Registering/Invited Model**
- **Registering**: Users who start fresh (become managers)
- **Invited**: Users who have a manager's code (become workers)
- One manager → one worker (MVP constraint for simplicity)
- Workers cannot register without a code

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

### **7. Simple Storage Interface**
Functions instead of classes for MVP simplicity:
```python
# Easy to understand
user = database.get_user(user_id)
history = conversations.get_conversation_history(user1, user2)

# Future: Replace internals without changing these calls
```

### **8. Normalized Conversation Keys**
- Key format: `"lowerID_higherID"` (always sorted)
- Manager ID: 9999, Worker ID: 1111 → Key: `"1111_9999"`
- Prevents duplication, enables easy lookup
- Works for one-to-one conversations

---

## **Data Models**

### **User Data (users.json)**

**Manager:**
```json
{
  "user_id": {
    "language": "English",
    "gender": "Female",
    "role": "manager",
    "industry": "dairy_farm",
    "code": "FARM-1234",
    "worker": "worker_id" or null
  }
}
```

**Worker:**
```json
{
  "user_id": {
    "language": "Spanish",
    "gender": "Male",
    "role": "worker",
    "manager": "manager_id"
  }
}
```

### **Conversation History (conversations.json)**
```json
{
  "user1_user2": [
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
}
```

---

## **Scaling Path**

### **Storage Scalability**

| Phase | Users | Storage | Action |
|-------|-------|---------|--------|
| MVP | < 500 | Single JSON files | ✅ Current |
| Growth | 500-2,000 | Separate JSON per conversation | Split conversations.json |
| Scale | > 2,000 | PostgreSQL | Migrate database.py & conversations.py |

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
| MVP | Railway (single instance) | $5-12/month |
| Production | Railway (scaled) | $20-50/month |
| Enterprise | Multi-region, load balanced | $100+/month |

---

## **Migration Strategies**

### **To Swap Database (JSON → PostgreSQL):**
1. Install: `pip install psycopg2` or use Supabase SDK
2. Rewrite `database.py` and `conversations.py` internals
3. Keep same function signatures
4. **No changes needed in bot.py** ✅
5. Migrate existing JSON data with simple script

### **To Add LLM Provider:**
1. Add credentials to `secrets.json`
2. Add model config to `config.json`
3. Add `translate_with_newprovider()` in `translator.py`
4. Update `translate()` routing logic
5. Change `translation_provider` in config

### **To Split Conversations to Separate Files:**
1. Create `conversations/` directory
2. Update `conversations.py`:
   - Change `load_conversations()` to `load_conversation(key)`
   - Save each pair to `conversations/{key}.json`
3. **No changes in bot.py** ✅

### **Local → Cloud Deployment:**
1. ✅ Create Railway account
2. ✅ Connect GitHub repository
3. ✅ Set environment variables (secrets)
4. ✅ Add `requirements.txt`, `Procfile`, `runtime.txt`
5. ✅ Push code → auto-deploy

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
- Code-based invitation system
- One-to-one manager-worker model
- Commands: `/start`, `/help`, `/mycode`, `/reset`

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

### **Environment:**
- **Local**: Uses `secrets.json` for API keys
- **Railway**: Uses environment variables (TELEGRAM_TOKEN, CLAUDE_API_KEY, etc.)

### **Bot Link:**
https://t.me/FarmTranslateBot

---

## **Important Constraints**

1. **One worker per manager** (MVP only)
2. **Code-based invitations** (no contact/username workarounds due to Telegram API limitations)
3. **Manager = anyone who selects "Registering"** during /start
4. **Worker = anyone who selects "Invited"** and enters a code
5. **Industry selected by manager**, worker inherits it
6. **Gender required** for translation accuracy in gendered languages