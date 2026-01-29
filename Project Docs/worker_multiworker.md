## **Updated Multi-Worker Implementation Summary**

### **What Changed:**

**BEFORE (Single Worker):**
- Manager → 1 Worker only
- Manager data: `'worker': 'worker_id'` (single string)
- Worker data: `'manager': 'manager_id'` (single string)
- Each bot instance handled same single worker

**AFTER (Multi-Worker via Multiple Bots):**
- Manager → Up to 5 Workers (one per bot)
- Manager data: `'workers': [{worker_id, bot_id, status, registered_at}, ...]` (array), `'pending_bots': []` (array)
- Worker data: `'manager': 'manager_id'`, `'bot_id': 'bot2'` (added bot_id field)
- Each bot instance handles its own specific worker

---

### **Architecture:**

**5 Bot Deployment:**
- Bot 1, Bot 2, Bot 3, Bot 4, Bot 5 (separate Railway services)
- Same codebase (`bot.py`)
- Different environment variables per bot:
  - `TELEGRAM_TOKEN` (unique per bot) - service-scoped
  - `BOT_ID` ('bot1', 'bot2', etc.) - service-scoped
- Shared environment variables (project-scoped):
  - `TELEGRAM_TOKEN_BOT1` through `TELEGRAM_TOKEN_BOT5` (for cross-bot messaging in `/addworker`)
- Shared PostgreSQL database
- Each bot chat = 1 worker = separate Telegram contact for manager

**Bot Self-Awareness:**
- Each bot reads `BOT_ID` from environment
- Routes messages to/from worker connected to THAT bot only
- Manager in Bot 2 chat → talks to Bot 2's worker only

**Cross-Bot Messaging:**
- `/addworker` command can send messages from any bot
- Uses shared `TELEGRAM_TOKEN_BOT1-5` variables to instantiate other bot clients
- Example: Bot 1 runs `/addworker` → Creates Bot 2 client → Sends greeting from Bot 2

---

### **Code Changes Made:**

**1. Registration (`gender_selected()`):**
- Manager: Initialize `workers: []` array and `pending_bots: []` array
- Worker: Add `bot_id` field when registering
- Append worker to manager's `workers` array (not replace single field)
- Check if worker already exists on THIS bot before connecting
- Remove bot from `pending_bots` when worker successfully connects ✅

**2. Message Routing (`handle_message()`):**
- Find worker where `bot_id == current_bot_id`
- Route message to that specific worker
- Worker→Manager routing unchanged (already unique)

**3. Task Creation (`handle_task_creation()`):**
- Find worker on current bot before creating task
- Task database already supports multiple workers (has worker_id column)

**4. Commands Updated:**
- `/mycode`: Shows all workers across all bots
- `/tasks`: Groups tasks by worker name (fetched from Telegram)
- `/daily`: Aggregates messages from ALL workers, groups action items by worker name
- `/reset`: Loops through all workers in array, cleans up each
- `/addworker`: ✅ UPDATED with pending_bots logic:
  - Checks if manager has pending invitation → Show "complete invitation first"
  - Checks if current bot has worker → Show "connect worker first"
  - Finds free bot, adds to `pending_bots` array
  - Sends proactive greeting with invite link

**5. Menu System:**
- Added `/addworker` button to manager's menu
- Callback handler routes to `addworker_command()`

**6. Media Forwarding (`handle_media()`):**
- Find worker on current bot before forwarding

**7. Translation Action Items (`translator.py`):**
- Groups messages by worker_name before generating action items
- Output format includes worker names as headers

**8. Migration Script (`migrate_to_multiworker.py`):**
- Converts existing `worker: 'id'` → `workers: [{worker_id: 'id', bot_id: 'bot1', ...}]`
- Adds `bot_id: 'bot1'` to existing workers (assumes bot1)
- Run once after deployment ✅ COMPLETED

**9. Pending Invitations System:** ✅ NEW
- `pending_bots` array tracks bots with incomplete invitations
- Prevents double-assignment of same bot
- Enforces sequential workflow (complete current invitation before starting next)
- Auto-cleared when worker connects
- Uses `.get('pending_bots', [])` pattern (no migration needed)

---

### **User Experience:**

**Manager Flow:**
1. Registers on Bot 1 → Gets invite code
2. Worker 1 uses code → Connects via Bot 1 (bot1 removed from pending_bots)
3. Manager types `/addworker` in Bot 1
   - ✅ Bot checks: Bot 1 has worker? YES
   - ✅ Bot checks: Any pending invitations? NO
   - ✅ Assigns Bot 2, adds to `pending_bots: ['bot2']`
4. Bot 2 proactively sends greeting + share button to manager
5. Manager opens Bot 2 → Sees invite waiting
6. If manager tries `/addworker` again (from Bot 1 or Bot 2):
   - ❌ "You have a pending invitation on BOT2. Please complete that first."
7. Manager shares invite → Worker 2 connects via Bot 2 (bot2 removed from pending_bots)
8. Manager's Telegram chat list shows:
   - "FarmTranslateBot" (rename to "John")
   - "BridgeOS_2bot" (rename to "Maria")
9. Each chat = separate worker (native Telegram contact experience)

**Message Routing:**
- Manager in Bot 1 chat → Messages go to Worker 1 only
- Manager in Bot 2 chat → Messages go to Worker 2 only
- No `/switch` command needed (bot context = worker context)

**Aggregated Views:**
- `/tasks`: Shows all tasks from all workers, grouped by name
- `/daily`: Shows action items from all workers, grouped by name
- Both commands work from ANY bot (aggregate across all bots)

**Sequential Workflow Enforcement:** ✅ NEW
- Manager can only have one pending invitation at a time
- Must complete current invitation before starting next
- Prevents confusion and double-assignments
- Clear error messages with links to pending bot

---

### **Railway Configuration:**

**Service-Scoped Variables (per bot):**
```
worker-bot1:
  TELEGRAM_TOKEN = bot1_token
  BOT_ID = bot1

worker-bot2:
  TELEGRAM_TOKEN = bot2_token
  BOT_ID = bot2
  
(etc. for bot3, bot4, bot5)
```

**Project-Scoped Shared Variables:**
```
TELEGRAM_TOKEN_BOT1 = bot1_token
TELEGRAM_TOKEN_BOT2 = bot2_token
TELEGRAM_TOKEN_BOT3 = bot3_token
TELEGRAM_TOKEN_BOT4 = bot4_token
TELEGRAM_TOKEN_BOT5 = bot5_token
```

**Why Both?**
- Service-scoped: Each bot starts with its own token
- Shared: `/addworker` can send messages AS other bots (proactive greeting)

---

### **Completed Features:** ✅

1. ✅ Multi-worker data structure (`workers` array)
2. ✅ Bot-aware routing (each bot handles its worker)
3. ✅ Cross-bot messaging (proactive greetings)
4. ✅ Aggregated views (`/tasks`, `/daily`)
5. ✅ Migration script (single worker → multi-worker)
6. ✅ **Pending invitations tracking** (`pending_bots` array)
7. ✅ **Sequential workflow enforcement** (one pending invitation at a time)
8. ✅ **Auto-cleanup** (bot removed from pending when worker connects)
9. ✅ **Clear UX** (error messages with bot links)

---

### **Still TODO:**

1. **I18N** - Translation strings for `/addworker` error messages:
   - `addworker.pending_invitation`
   - `addworker.no_worker_on_current_bot`
2. **Dashboard updates** - Show `workers` array and `pending_bots` in manager detail page
3. **Subscription logic** - Pricing for multiple workers (business decision)
4. **Help text updates** - Explain multi-bot usage in `/help` command
5. **`/removeworker` command** - Let manager remove specific worker (alternative to worker's `/reset`)
6. **Error handling** - What if Bot 2 doesn't have token configured? (graceful degradation)
7. **Bot 4 & 5 creation** - Currently only 3 bots deployed
8. **Testing** - Test full flow: register → add worker → pending check → connect → add another

---

### **Database Schema (unchanged):**
- `users` table: JSONB column stores manager/worker data
  - Manager: `{workers: [...], pending_bots: [...]}`
  - Worker: `{manager: '...', bot_id: '...'}`
- `tasks` table: Already has `worker_id` column (multi-worker ready)
- `message_history` table: Uses `conversation_key` (manager_worker pairs)
- `conversations` table: Uses `conversation_key` (translation context)
- No schema changes needed - just data structure within JSONB

---

### **Key Design Decisions:**

**✅ Multiple Bots (Chosen):**
- Natural UX: Each bot = separate contact in Telegram
- Zero cognitive load: Manager just opens different chats
- Native Telegram experience (rename bots to worker names)
- Covers 80% of use cases (1-5 workers)

**✅ Pending Invitations Tracking (Chosen):**
- Simple array in manager data (no new tables)
- Auto-cleanup when worker connects
- Enforces sequential workflow (clearer UX)
- Uses `.get('pending_bots', [])` pattern (backwards compatible)

**❌ Single Bot with `/switch` (Rejected):**
- Confusing UX: One chat for multiple people
- Manager must remember to switch before messaging
- Error-prone: Might send to wrong worker
- Violates mental model of "one chat = one person"

**❌ Allow multiple pending invitations (Rejected):**
- Confusing: Manager might forget which bots have pending invites
- Harder to track: Multiple simultaneous invitations
- Edge cases: What if manager shares all 5 at once?
- Sequential is simpler and clearer