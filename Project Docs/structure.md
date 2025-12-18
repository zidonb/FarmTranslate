## **FarmTranslate - Architecture & Guidelines**

---

## **Coding Principles**

1. **KISS** - Simple, readable code. No fancy abstractions.
2. **Minimal** - Only what we need for MVP. No "what if" features.
3. **Smart structure** - Clean separation so we can swap parts later:
   - Translation logic → separate module (easy to swap providers)
   - Database → simple interface (easy to upgrade to PostgreSQL)
   - Bot handlers → clean functions (easy to add features)

---

## **File Structure**
```
farm-translate/
├── bot.py              # Main bot logic (handlers, commands, conversation flow)
├── translator.py       # Translation with multiple LLM providers
├── database.py         # JSON storage with clean interface
├── config.json         # Bot token + API keys + provider selection
├── users.json          # User data (auto-created)
└── docs/              # Documentation folder
    ├── summary.md      # Project overview
    └── structure.md    # This file
```

**4 core Python files + auto-generated data file**

---

## **Design Pattern: Separation of Concerns**

### **bot.py**
- Telegram bot handlers
- User registration flow
- Message routing logic
- No translation or database logic

### **translator.py**
- Provider-agnostic `translate()` function
- Provider-specific implementations:
  - `translate_with_claude()` - Strong system prompt
  - `translate_with_gemini()` - Schema-enforced JSON
  - `translate_with_openai()` - System prompt
- Easy to add new providers

### **database.py**
- Simple function interface: `get_user()`, `save_user()`, `get_all_users()`
- Currently: JSON file storage
- Future: Swap implementation to PostgreSQL without changing bot.py

### **config.json**
- Centralized configuration
- Multiple provider credentials
- Easy provider switching via `translation_provider` field

---

## **Key Design Decisions**

### **1. Provider Flexibility**
Different LLMs have different strengths:
- **Claude**: Best overall quality, strong system prompts
- **Gemini**: Schema enforcement prevents hallucinations
- **OpenAI**: Alternative option for comparison

### **2. Simple Storage Interface**
Functions instead of classes for MVP simplicity:
```python
# Easy to understand
user = database.get_user(user_id)

# Future: Replace internals without changing this call
# PostgreSQL, MongoDB, Redis - same interface
```

### **3. Indentation-Aware Code**
Python requires proper indentation for ALL lines including comments:
```python
# CORRECT
if condition:
    # This comment is indented
    code_here()

# WRONG - breaks code
if condition:
# This comment breaks indentation
    code_here()
```

---

## **Scaling Path**

### **Phase 1: MVP (Current)**
- JSON file storage
- Single LLM provider
- Local execution
- Manager/Worker only

### **Phase 2: Production**
- PostgreSQL database
- Cloud deployment (Railway/Render)
- Error handling & logging
- Rate limiting

### **Phase 3: Advanced**
- Message history context
- Multi-language context awareness
- Voice message support
- Analytics dashboard
- Payment integration

---

## **Migration Strategy**

### **To Swap Database:**
1. Rewrite `database.py` internals
2. Keep same function signatures
3. No changes needed in `bot.py`

### **To Add LLM Provider:**
1. Add credentials to `config.json`
2. Add `translate_with_newprovider()` in `translator.py`
3. Update `translate()` routing logic
4. Change `translation_provider` in config

### **To Deploy Cloud:**
1. Choose platform (Railway/Render)
2. Add requirements.txt
3. Set environment variables
4. Push code
5. Bot runs 24/7