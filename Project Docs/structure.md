# FarmTranslate - Architecture & Guidelines

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
    ├── summary.md          # Project overview
    ├── structure.md        # This file
    └── todo.md             # Development roadmap
```

---

## **Design Pattern: Separation of Concerns**

### **bot.py**
- Telegram bot handlers
- User registration flow (language → gender → role → code)
- Message routing logic
- Commands: `/start`, `/help`, `/mycode`
- No translation, database, or config logic

### **translator.py**
- Provider-agnostic `translate()` function
- Accepts conversation history for context
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
  "context": {
    "industry": "dairy farming",
    "description": "...",
    "history_size": 5
  },
  "languages": [...],
  "claude": { "model": "..." }
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

### **1. Configuration Split**
- **Problem**: Can't upload API keys to GitHub
- **Solution**: 
  - `config.json` = settings (safe to upload)
  - `secrets.json` = API keys (local only)
  - Environment variables = API keys (Railway)
- **Benefit**: Single `config.py` handles all sources

### **2. Provider Flexibility**
Different LLMs have different strengths:
- **Claude**: Best overall quality, strong system prompts, supports industry context
- **Gemini**: Schema enforcement prevents answering questions, very cheap
- **OpenAI**: Alternative option, structured outputs

**Switch providers by changing one line in config.json**

### **3. Conversation Context**
- Stores last N messages per conversation pair
- Sliding window (configurable via `history_size`)
- Helps with:
  - Pronouns ("she" = cow 115)
  - Ambiguous words ("heat" = estrus in dairy context)
  - Topic continuity
- Stores original language (not translated) for better LLM understanding

### **4. Gender-Aware Translation**
- Asks gender during registration
- Passes to translation prompt
- Critical for Hebrew, Arabic, Spanish, French
- Example: "You need to check" → "אתה צריך" (male) vs "את צריכה" (female)

### **5. Industry Context in Prompts**
- Configurable domain knowledge
- Example: "Check if cow is in heat" → "בדוק אם הפרה מיוחמת" (uses dairy terminology)
- Easy to customize per customer (dairy, construction, restaurant, etc.)

### **6. Simple Storage Interface**
Functions instead of classes for MVP simplicity:
```python
# Easy to understand
user = database.get_user(user_id)
history = conversations.get_conversation_history(user1, user2)

# Future: Replace internals without changing these calls
```

### **7. Normalized Conversation Keys**
- Key format: `"lowerID_higherID"` (always sorted)
- Manager ID: 9999, Worker ID: 1111 → Key: `"1111_9999"`
- Prevents duplication, enables easy lookup
- Scales to multiple workers per manager

---

## **Data Models**

### **User Data (users.json)**
```json
{
  "user_id": {
    "language": "English",
    "gender": "Male",
    "role": "manager",
    "code": "FARM-1234",
    "workers": ["worker_id_1", "worker_id_2"]
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
      "timestamp": "2025-12-20T10:30:00"
    },
    {
      "from": "user2",
      "text": "היא נראית בריאה",
      "lang": "Hebrew",
      "timestamp": "2025-12-20T10:31:00"
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

1. **Start**: Claude Sonnet (~$2/user/month at 50 msg/day)
2. **Test**: Gemini Flash (40x cheaper, ~$0.05/user/month)
3. **Optimize**: Reduce context size if needed
4. **Scale**: Use cheaper models for simple messages, Claude for complex

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