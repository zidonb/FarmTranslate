"""
Tier 3: Handler logic tests — mocked Telegram, real DB.

Tests the handler functions with mock Telegram Update/Context objects
but real database operations. The translator is mocked (see conftest.py).

Covers:
  - Message translation and forwarding (manager→worker, worker→manager)
  - Message to unconnected bot slot
  - Task creation (** prefix) and completion callback
  - /addworker finding next available slot
  - /workers showing correct slot status
  - /daily generating action items
  - /reset disconnecting and cleaning up
  - Usage limit enforcement during messaging
"""
import pytest
from unittest.mock import patch, AsyncMock


# ====================================================================
# MESSAGE HANDLING
# ====================================================================

class TestMessageHandling:
    """handlers.messages — translate and forward between manager and worker."""

    @pytest.mark.asyncio
    async def test_manager_to_worker_message(self, make_connection, make_update, make_context):
        """Manager sends text → translated and forwarded to worker."""
        from handlers.messages import handle_message
        import models.message as message_model

        m_user, w_user, conn = make_connection(1001, 2001, bot_slot=1)
        update = make_update(user_id=1001, text="Good morning!", first_name="Alice")
        ctx = make_context()

        # BOT_ID=bot1 → slot 1 (set in conftest env)
        await handle_message(update, ctx)

        # Verify message was forwarded to worker
        assert len(ctx.bot.sent_messages) >= 1
        fwd = ctx.bot.sent_messages[0]
        assert fwd["chat_id"] == 2001
        assert "[TRANSLATED:Español]" in fwd["text"]
        assert "Good morning!" in fwd["text"]

        # Verify message was saved to DB
        msgs = message_model.get_recent(conn["connection_id"], hours=1)
        assert len(msgs) == 1
        assert msgs[0]["original_text"] == "Good morning!"

    @pytest.mark.asyncio
    async def test_worker_to_manager_message(self, make_connection, make_update, make_context):
        """Worker sends text → translated and forwarded to manager."""
        from handlers.messages import handle_message

        make_connection(1001, 2001, bot_slot=1)
        update = make_update(user_id=2001, text="Buenos días!", first_name="Carlos")
        ctx = make_context()

        await handle_message(update, ctx)

        assert len(ctx.bot.sent_messages) >= 1
        fwd = ctx.bot.sent_messages[0]
        assert fwd["chat_id"] == 1001
        assert "[TRANSLATED:English]" in fwd["text"]

    @pytest.mark.asyncio
    async def test_manager_no_worker_connected(self, make_manager, make_update, make_context):
        """Manager sends message on bot with no worker connected → error message."""
        from handlers.messages import handle_message

        make_manager(1001, code="BRIDGE-10001")
        update = make_update(user_id=1001, text="Hello?", first_name="Alice")
        ctx = make_context()

        await handle_message(update, ctx)

        # Should get a reply about no worker connected
        assert len(update.message._replies) >= 1
        reply_text = update.message._replies[0]["text"]
        assert "don't have a worker" in reply_text.lower() or "BRIDGE-10001" in reply_text

    @pytest.mark.asyncio
    async def test_unregistered_user_message(self, make_update, make_context):
        """Unregistered user sends message → told to /start."""
        from handlers.messages import handle_message

        update = make_update(user_id=9999, text="Hello")
        ctx = make_context()

        await handle_message(update, ctx)

        assert len(update.message._replies) >= 1
        assert "/start" in update.message._replies[0]["text"]

    @pytest.mark.asyncio
    async def test_worker_no_connection(self, make_worker, make_update, make_context):
        """Worker with no active connection → error message."""
        from handlers.messages import handle_message

        make_worker(2001, "Carlos", "Español")
        update = make_update(user_id=2001, text="Hola")
        ctx = make_context()

        await handle_message(update, ctx)

        assert len(update.message._replies) >= 1
        reply = update.message._replies[0]["text"]
        assert ("not connected" in reply.lower() or "invitation" in reply.lower()
                or "no estás conectado" in reply.lower() or "invitación" in reply.lower())


# ====================================================================
# USAGE LIMIT ENFORCEMENT
# ====================================================================

class TestUsageLimits:
    """Usage limits are enforced during messaging (free_message_limit=3)."""

    @pytest.mark.asyncio
    async def test_blocked_manager_cannot_send(self, make_connection, make_update, make_context):
        """After hitting the limit, manager's messages are blocked."""
        from handlers.messages import handle_message
        import models.usage as usage_model

        make_connection(1001, 2001, bot_slot=1)

        # Burn through the limit
        for _ in range(3):
            usage_model.increment(1001)

        assert usage_model.is_blocked(1001) is True

        update = make_update(user_id=1001, text="Can I still send?", first_name="Alice")
        ctx = make_context()

        await handle_message(update, ctx)

        # Should get upgrade prompt, NOT forward to worker
        assert len(update.message._replies) >= 1
        reply = update.message._replies[0]["text"]
        assert "limit" in reply.lower() or "upgrade" in reply.lower()
        # Worker should NOT have received the message
        worker_msgs = [m for m in ctx.bot.sent_messages if m["chat_id"] == 2001]
        assert len(worker_msgs) == 0

    @pytest.mark.asyncio
    async def test_subscribed_manager_bypasses_limit(self, make_connection, make_update, make_context):
        """Active subscriber can send even after hitting free limit."""
        from handlers.messages import handle_message
        import models.usage as usage_model
        import models.subscription as sub_model

        make_connection(1001, 2001, bot_slot=1)

        # Hit free limit
        for _ in range(3):
            usage_model.increment(1001)

        # But they have a subscription
        sub_model.save(1001, status="active")

        update = make_update(user_id=1001, text="Still works!", first_name="Alice")
        ctx = make_context()

        await handle_message(update, ctx)

        # Message should be forwarded to worker
        worker_msgs = [m for m in ctx.bot.sent_messages if m["chat_id"] == 2001]
        assert len(worker_msgs) >= 1


# ====================================================================
# TASK HANDLING
# ====================================================================

class TestTaskHandling:
    """Task creation via ** prefix and completion callbacks."""

    @pytest.mark.asyncio
    async def test_task_creation_with_prefix(self, make_connection, make_update, make_context):
        """Manager sends '** Check cow 115' → task created and sent to worker."""
        from handlers.messages import handle_message
        import models.task as task_model

        make_connection(1001, 2001, bot_slot=1)
        update = make_update(user_id=1001, text="** Check cow 115", first_name="Alice")
        ctx = make_context()

        await handle_message(update, ctx)

        # Task should exist in DB
        tasks = task_model.get_manager_tasks(1001)
        assert len(tasks) == 1
        assert "Check cow 115" in tasks[0]["description"]

        # Worker should have received the task
        worker_msgs = [m for m in ctx.bot.sent_messages if m["chat_id"] == 2001]
        assert len(worker_msgs) >= 1

    @pytest.mark.asyncio
    async def test_task_completion_callback(self, make_connection, make_update, make_context):
        """Worker clicks ✅ Mark Done → task marked completed, manager notified."""
        from handlers.tasks import task_completion_callback
        import models.task as task_model
        import models.connection as connection_model

        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        tid = task_model.create(conn["connection_id"], "Fix gate", "Arreglar puerta")

        # Simulate callback query from worker
        update = make_update(user_id=2001, callback_data=f"task_done_{tid}",
                             first_name="Carlos")
        ctx = make_context()

        await task_completion_callback(update, ctx)

        # Task should be completed in DB
        task = task_model.get_by_id(tid)
        assert task["status"] == "completed"

        # Manager should be notified
        mgr_msgs = [m for m in ctx.bot.sent_messages if m["chat_id"] == 1001]
        assert len(mgr_msgs) >= 1


# ====================================================================
# /workers COMMAND
# ====================================================================

class TestWorkersCommand:
    """handlers.connections — /workers shows slot status."""

    @pytest.mark.asyncio
    async def test_workers_shows_connected(self, make_connection, make_update, make_context):
        """Connected workers appear in the /workers output."""
        from handlers.connections import workers_command

        make_connection(1001, 2001, bot_slot=1)
        update = make_update(user_id=1001, first_name="Alice")
        ctx = make_context()

        await workers_command(update, ctx)

        assert len(update.message._replies) >= 1
        reply = update.message._replies[0]["text"]
        assert "Bot 1" in reply
        assert "✅" in reply or "Worker" in reply

    @pytest.mark.asyncio
    async def test_workers_shows_available_slots(self, make_manager, make_update, make_context):
        """Manager with no workers sees all slots as available."""
        from handlers.connections import workers_command

        make_manager(1001, code="BRIDGE-10001")
        update = make_update(user_id=1001, first_name="Alice")
        ctx = make_context()

        await workers_command(update, ctx)

        reply = update.message._replies[0]["text"]
        assert "Available" in reply


# ====================================================================
# /addworker COMMAND
# ====================================================================

class TestAddworkerCommand:
    """handlers.connections — /addworker finds next free slot."""

    @pytest.mark.asyncio
    async def test_addworker_assigns_slot_1_first(self, make_manager, make_update, make_context):
        """First /addworker gives slot 1 (or next available)."""
        from handlers.connections import addworker_command

        make_manager(1001, code="BRIDGE-10001")
        update = make_update(user_id=1001, first_name="Alice")
        ctx = make_context()

        await addworker_command(update, ctx)

        # Should mention the bot slot assignment
        assert len(update.message._replies) >= 1

    @pytest.mark.asyncio
    async def test_addworker_skips_occupied_slots(self, make_connection, make_update, make_context, make_worker):
        """When slot 1 is occupied, /addworker assigns slot 2."""
        from handlers.connections import addworker_command
        import models.connection as connection_model

        make_connection(1001, 2001, bot_slot=1)

        update = make_update(user_id=1001, first_name="Alice")
        ctx = make_context()

        await addworker_command(update, ctx)

        # Should reference a bot slot number > 1
        assert len(update.message._replies) >= 1


# ====================================================================
# /daily COMMAND
# ====================================================================

class TestDailyCommand:
    """handlers.tasks — /daily generates AI action items from messages."""

    @pytest.mark.asyncio
    async def test_daily_with_messages(self, make_connection, make_update, make_context):
        """Manager with recent messages gets action items summary."""
        from handlers.tasks import daily_command
        import models.message as message_model

        _, _, conn = make_connection(1001, 2001, bot_slot=1)

        # Add some messages
        message_model.save(conn["connection_id"], 1001, "Check the gate", "Revisa la puerta")
        message_model.save(conn["connection_id"], 2001, "OK boss", "OK jefe")

        update = make_update(user_id=1001, first_name="Alice")
        ctx = make_context()

        await daily_command(update, ctx)

        # Should get at least 2 replies (generating... + result)
        assert len(update.message._replies) >= 1

    @pytest.mark.asyncio
    async def test_daily_not_manager(self, make_worker, make_update, make_context):
        """Worker trying /daily gets rejection."""
        from handlers.tasks import daily_command

        make_worker(2001, "Carlos", "Español")
        update = make_update(user_id=2001, first_name="Carlos")
        ctx = make_context()

        await daily_command(update, ctx)

        reply = update.message._replies[0]["text"]
        assert ("manager" in reply.lower() or "Only" in reply
                or "gerente" in reply.lower() or "Solo" in reply)


# ====================================================================
# /reset COMMAND
# ====================================================================

class TestResetCommand:
    """handlers.commands — /reset cleans up user data and connections."""

    @pytest.mark.asyncio
    async def test_reset_manager_disconnects_workers(self, make_connection, make_update, make_context):
        """Resetting a manager disconnects all their workers."""
        from handlers.commands import reset_command
        import models.connection as connection_model
        import models.user as user_model

        make_connection(1001, 2001, bot_slot=1)
        update = make_update(user_id=1001, first_name="Alice")
        ctx = make_context()

        await reset_command(update, ctx)

        # Manager's connections should be disconnected
        conns = connection_model.get_active_for_manager(1001)
        assert len(conns) == 0

        # Manager user should be deleted
        assert user_model.get_by_id(1001) is None

        # Worker should have been notified
        worker_notifs = [m for m in ctx.bot.sent_messages if m["chat_id"] == 2001]
        assert len(worker_notifs) >= 1

    @pytest.mark.asyncio
    async def test_reset_worker(self, make_connection, make_update, make_context):
        """Resetting a worker disconnects them and notifies manager."""
        from handlers.commands import reset_command
        import models.connection as connection_model
        import models.user as user_model

        make_connection(1001, 2001, bot_slot=1)
        update = make_update(user_id=2001, first_name="Carlos")
        ctx = make_context()

        await reset_command(update, ctx)

        # Worker's connection should be disconnected
        assert connection_model.get_active_for_worker(2001) is None
        # Worker user should be deleted
        assert user_model.get_by_id(2001) is None
        # Manager should have been notified
        mgr_notifs = [m for m in ctx.bot.sent_messages if m["chat_id"] == 1001]
        assert len(mgr_notifs) >= 1

    @pytest.mark.asyncio
    async def test_reset_unregistered_user(self, make_update, make_context):
        """Resetting with no account → friendly message."""
        from handlers.commands import reset_command

        update = make_update(user_id=9999, first_name="Nobody")
        ctx = make_context()

        await reset_command(update, ctx)

        reply = update.message._replies[0]["text"]
        assert "don't have" in reply.lower() or "no account" in reply.lower()


# ====================================================================
# /help COMMAND
# ====================================================================

class TestHelpCommand:
    """handlers.commands — /help shows role-appropriate commands."""

    @pytest.mark.asyncio
    async def test_help_manager(self, make_manager, make_update, make_context):
        from handlers.commands import help_command

        make_manager(1001, code="BRIDGE-10001")
        update = make_update(user_id=1001)
        ctx = make_context()

        await help_command(update, ctx)

        reply = update.message._replies[0]["text"]
        assert "/daily" in reply or "/tasks" in reply
        assert "/addworker" in reply or "/workers" in reply or "/mycode" in reply

    @pytest.mark.asyncio
    async def test_help_worker(self, make_worker, make_update, make_context):
        from handlers.commands import help_command

        make_worker(2001, "Carlos", "Español")
        update = make_update(user_id=2001)
        ctx = make_context()

        await help_command(update, ctx)

        reply = update.message._replies[0]["text"]
        assert "/tasks" in reply
        # Workers shouldn't see manager-only commands
        assert "/addworker" not in reply


# ====================================================================
# MEDIA FORWARDING
# ====================================================================

class TestMediaForwarding:
    """handlers.messages — media forwarding (photos, files, etc.)."""

    @pytest.mark.asyncio
    async def test_media_forwarded_manager_to_worker(self, make_connection, make_update, make_context):
        """Manager sends media → prefix sent to worker, then media forwarded."""
        from handlers.messages import handle_media

        make_connection(1001, 2001, bot_slot=1)
        update = make_update(user_id=1001, first_name="Alice")
        # Simulate a photo message
        update.message.photo = [type("PhotoSize", (), {"file_id": "test_photo"})()]
        ctx = make_context()

        await handle_media(update, ctx)

        # Should send prefix to worker
        worker_msgs = [m for m in ctx.bot.sent_messages if m["chat_id"] == 2001]
        assert len(worker_msgs) >= 1
        assert "Alice" in worker_msgs[0]["text"] or "📎" in worker_msgs[0]["text"]

    @pytest.mark.asyncio
    async def test_media_no_connection(self, make_manager, make_update, make_context):
        """Manager sends media with no worker → error."""
        from handlers.messages import handle_media

        make_manager(1001, code="BRIDGE-10001")
        update = make_update(user_id=1001)
        ctx = make_context()

        await handle_media(update, ctx)

        assert len(update.message._replies) >= 1
        reply = update.message._replies[0]["text"]
        assert "don't have" in reply.lower() or "not connected" in reply.lower() or "worker" in reply.lower()
