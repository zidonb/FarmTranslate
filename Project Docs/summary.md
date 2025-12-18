## **FarmTranslate MVP - Complete Plan**

---

### **What It Does**
- Telegram bot that translates messages between managers and workers
- Each manager gets unique code to share with their workers
- One bot handles unlimited managers, each with multiple workers
- Supports multiple LLM providers (Claude, Gemini, OpenAI)

---

### **User Flow**

**Manager:**
1. `/start` → Select language (English/Spanish/Hebrew/Thai/Arabic/Turkish/French/German)
2. Bot asks: "Are you a Manager or Worker?"
3. Select "Manager" → Bot generates unique code (e.g., FARM-8472)
4. Share code with workers

**Worker:**
1. `/start` → Select language
2. Bot asks: "Are you a Manager or Worker?"
3. Select "Worker" → Bot asks for manager's code
4. Enter FARM-8472 → ✅ Connected!

**Chatting:**
- Manager messages bot → translates to worker's language → sends to worker
- Worker messages bot → translates to manager's language → sends to manager
- Both see: "🗣️ From [Telegram Name]: [translated message]"
- No confirmation messages (silent delivery)

---

### **Security Rules**
- ✅ Manager can only message their registered workers
- ✅ Worker can only message their registered manager
- ✅ One worker = one manager (MVP)
- ✅ One manager = multiple workers
- ✅ Only users who did `/start` can connect
- ✅ Unique code generation with collision prevention

---

### **Tech Stack**
- Python 3.11
- python-telegram-bot library
- Anthropic Claude API (primary translator)
- Google Gemini API (optional, with schema enforcement)
- OpenAI API (optional)
- JSON file storage (store connections)
- Runs locally (future: Railway/Render for 24/7)

---

### **Translation Features**
- Configurable LLM provider (Claude/Gemini/OpenAI)
- Strong system prompts to prevent answering questions (Claude/OpenAI)
- Schema-enforced JSON output to prevent hallucinations (Gemini)
- Uses Telegram names for personalization

---

### **Data Structure**
```json
{
  "manager_123": {
    "language": "English",
    "role": "manager",
    "code": "FARM-8472",
    "workers": ["worker_456"]
  },
  "worker_456": {
    "language": "Spanish",
    "role": "worker",
    "manager": "manager_123"
  }
}
```

---

### **Future Roadmap (Post-MVP)**
- Message history context for better translations
- Cloud deployment (Railway/Render) for 24/7 availability
- PostgreSQL database
- Multi-worker switching for managers
- Voice message translation
- Admin dashboard
- Payment integration