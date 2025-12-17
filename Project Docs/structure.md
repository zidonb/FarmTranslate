**Perfect principles! 🎯**

---

## **Coding Guidelines - Confirmed**

1. **KISS** - Simple, readable code. No fancy abstractions.
2. **Minimal** - Only what we need for MVP. No "what if" features.
3. **Smart structure** - Clean separation so we can swap parts later:
   - Translation logic → separate function (easy to replace Claude with Google Translate)
   - Database → simple module (easy to swap JSON → PostgreSQL)
   - Bot handlers → clean functions (easy to add features)

---

## **File Structure (Simple)**

```
farm-translate/
├── bot.py              # Main bot logic (handlers, commands)
├── translator.py       # Translation function (Claude API)
├── database.py         # Load/save JSON data
├── config.json         # Bot token + API key
└── users.json          # User data (auto-created)
```

**That's it. 4 Python files.**

---

## **Design Pattern: Separation of Concerns**

```python
# bot.py - handles Telegram
# translator.py - handles translation
# database.py - handles data storage

# Later want PostgreSQL? Replace database.py
# Later want Google Translate? Replace translator.py
# Bot logic stays the same
```

