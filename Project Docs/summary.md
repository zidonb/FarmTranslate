## **FarmTranslate MVP - Complete Plan**

---

### **What It Does**
- Telegram bot that translates messages between farmers and employees
- Each farmer gets unique code to share with their employees
- One bot handles unlimited farmers, each with multiple employees

---

### **User Flow**

**Farmer:**
1. `/start` → Select language (English/Spanish/Hebrew/etc)
2. Bot asks: "Are you Employer or Employee?"
3. Select "Employer" → Bot generates unique code (e.g., FARM-8472)
4. Share code with employee

**Employee:**
1. `/start` → Select language
2. Bot asks: "Are you Employer or Employee?"
3. Select "Employee" → Bot asks for employer's code
4. Enter FARM-8472 → ✅ Connected!

**Chatting:**
- Farmer messages bot → translates to Spanish → sends to employee
- Employee messages bot → translates to English → sends to farmer
- Both see: "🗣️ From [Name]: [translated message]"

---

### **Security Rules**
- ✅ Farmer can only message their registered employees
- ✅ Employee can only message their registered employer
- ✅ One employee = one employer (MVP)
- ✅ One employer = multiple employees
- ✅ Only users who did `/start` can connect

---

### **Tech Stack**
- Python 3.11
- python-telegram-bot library
- Claude API (translation)
- JSON file (store connections)
- Runs on your computer (later: Railway/Render)

---

### **Data Structure**
```json
{
  "farmer_123": {
    "language": "en",
    "role": "employer",
    "code": "FARM-8472",
    "employees": ["employee_456"]
  },
  "employee_456": {
    "language": "es",
    "role": "employee",
    "employer": "farmer_123"
  }
}
```

