"""
Tier 3b: Edge cases — constraint enforcement, capacity limits, orphaned data, Unicode.

Tests scenarios that might occur under concurrent usage or unusual sequences:
  - Race condition: duplicate bot slot assignment (DB constraint catches it)
  - Race condition: worker double-connection (DB constraint catches it)
  - Manager with 5 workers (max capacity) then /addworker
  - Worker whose manager got deleted
  - Manager whose worker got deleted
  - Messages after connection disconnected
  - Subscription expiry mid-conversation
  - Unicode/RTL text handling (Hebrew, Arabic, Thai)
"""
import pytest
from datetime import datetime, timedelta, timezone


# ====================================================================
# DATABASE CONSTRAINT ENFORCEMENT
# ====================================================================

class TestConstraintEnforcement:

    def test_two_workers_same_slot(self, make_manager, make_worker):
        from models.connection import SlotOccupiedError
        import models.connection as connection_model

        make_manager(1001, code="BRIDGE-10001")
        make_worker(2001, "Worker1")
        make_worker(2002, "Worker2")

        connection_model.create(1001, 2001, bot_slot=2)
        with pytest.raises(SlotOccupiedError):
            connection_model.create(1001, 2002, bot_slot=2)

    def test_worker_two_managers(self, make_manager, make_worker):
        from models.connection import WorkerAlreadyConnectedError
        import models.connection as connection_model

        make_manager(1001, code="BRIDGE-10001")
        make_manager(1002, name="Manager2", code="BRIDGE-10002")
        make_worker(2001, "SharedWorker")

        connection_model.create(1001, 2001, bot_slot=1)
        with pytest.raises(WorkerAlreadyConnectedError):
            connection_model.create(1002, 2001, bot_slot=1)

    def test_disconnect_frees_constraints(self, make_manager, make_worker):
        """After disconnect, both slot and worker constraints are freed."""
        import models.connection as connection_model

        make_manager(1001, code="BRIDGE-10001")
        make_manager(1002, name="Manager2", code="BRIDGE-10002")
        make_worker(2001, "Worker1")

        cid = connection_model.create(1001, 2001, bot_slot=1)
        connection_model.disconnect(cid)

        # Worker can now connect to different manager
        new_cid = connection_model.create(1002, 2001, bot_slot=1)
        assert connection_model.get_by_id(new_cid)["status"] == "active"


# ====================================================================
# CAPACITY LIMITS
# ====================================================================

class TestCapacityLimits:

    def test_five_workers_all_slots(self, make_manager, make_worker):
        import models.connection as connection_model
        make_manager(1001, code="BRIDGE-10001")
        for slot in range(1, 6):
            make_worker(2000 + slot, f"Worker{slot}")
            connection_model.create(1001, 2000 + slot, slot)
        assert len(connection_model.get_active_for_manager(1001)) == 5

    def test_no_slot_for_sixth_worker(self, make_manager, make_worker):
        from models.connection import SlotOccupiedError
        import models.connection as connection_model

        make_manager(1001, code="BRIDGE-10001")
        for slot in range(1, 6):
            make_worker(2000 + slot, f"Worker{slot}")
            connection_model.create(1001, 2000 + slot, slot)

        make_worker(2006, "Worker6")
        for slot in range(1, 6):
            with pytest.raises(SlotOccupiedError):
                connection_model.create(1001, 2006, slot)

    @pytest.mark.asyncio
    async def test_addworker_at_capacity(self, make_manager, make_worker,
                                          make_update, make_context):
        from handlers.connections import addworker_command
        import models.connection as connection_model

        make_manager(1001, code="BRIDGE-10001")
        for slot in range(1, 6):
            make_worker(2000 + slot, f"W{slot}")
            connection_model.create(1001, 2000 + slot, slot)

        update = make_update(user_id=1001, first_name="Alice")
        ctx = make_context()
        await addworker_command(update, ctx)

        reply = update.message._replies[0]["text"]
        assert "all" in reply.lower() or "5" in reply or "slot" in reply.lower()


# ====================================================================
# ORPHANED DATA
# ====================================================================

class TestOrphanedData:

    @pytest.mark.asyncio
    async def test_worker_msg_after_manager_deleted(self, make_connection,
                                                      make_update, make_context):
        from handlers.messages import handle_message
        import models.user as user_model
        import models.manager as manager_model
        import models.connection as connection_model

        make_connection(1001, 2001, bot_slot=1)
        # Disconnect first, then soft-delete, then hard-delete
        conns = connection_model.get_active_for_manager(1001)
        for c in conns:
            connection_model.disconnect(c['connection_id'])
        manager_model.soft_delete(1001)
        user_model.delete(1001)

        update = make_update(user_id=2001, text="Hello?")
        ctx = make_context()
        await handle_message(update, ctx)

        reply = update.message._replies[0]["text"]
        assert ("not connected" in reply.lower() or "no longer" in reply.lower()
                or "no estás conectado" in reply.lower() or "invitación" in reply.lower())

    @pytest.mark.asyncio
    async def test_manager_msg_after_worker_deleted(self, make_connection,
                                                      make_update, make_context):
        from handlers.messages import handle_message
        import models.user as user_model
        import models.worker as worker_model
        import models.connection as connection_model

        make_connection(1001, 2001, bot_slot=1)
        # Disconnect first, then soft-delete, then hard-delete
        conn = connection_model.get_active_for_worker(2001)
        if conn:
            connection_model.disconnect(conn['connection_id'])
        worker_model.soft_delete(2001)
        user_model.delete(2001)

        update = make_update(user_id=1001, text="Hello worker?")
        ctx = make_context()
        await handle_message(update, ctx)

        reply = update.message._replies[0]["text"]
        assert ("no worker" in reply.lower() or "not connected" in reply.lower()
                or "don't have" in reply.lower() or "invitation" in reply.lower()
                or "no longer" in reply.lower())


# ====================================================================
# SUBSCRIPTION EXPIRY MID-CONVERSATION
# ====================================================================

class TestSubscriptionExpiry:

    @pytest.mark.asyncio
    async def test_subscription_expires_then_blocked(self, make_connection,
                                                       make_update, make_context):
        """
        Manager has subscription, burns through free limit, sub expires →
        next message is blocked.
        """
        from handlers.messages import handle_message
        import models.subscription as sub_model
        import models.usage as usage_model

        make_connection(1001, 2001, bot_slot=1)

        # Subscribe and use lots of messages
        sub_model.save(1001, status="active")
        for _ in range(5):
            usage_model.increment(1001)

        # Now subscription expires
        past = datetime.now(timezone.utc) - timedelta(days=1)
        sub_model.update_status(1001, "expired", ends_at=past)

        update = make_update(user_id=1001, text="Can I send?", first_name="Alice")
        ctx = make_context()
        await handle_message(update, ctx)

        reply = update.message._replies[0]["text"]
        assert any(kw in reply.lower()
                   for kw in ["limit", "upgrade", "subscription", "free"])


# ====================================================================
# UNICODE / RTL TEXT HANDLING
# ====================================================================

class TestUnicodeHandling:
    """Verify Hebrew, Arabic, Thai, and mixed text survive DB round-trips."""

    def test_hebrew_text_in_messages(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        hebrew = "שלום! מה שלומך היום?"
        message_model.save(conn["connection_id"], 1001, hebrew, "Hello! How are you?")
        msgs = message_model.get_recent(conn["connection_id"])
        assert msgs[0]["original_text"] == hebrew

    def test_arabic_text_in_messages(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        arabic = "مرحبا! كيف حالك اليوم؟"
        message_model.save(conn["connection_id"], 1001, arabic, "Hello!")
        msgs = message_model.get_recent(conn["connection_id"])
        assert msgs[0]["original_text"] == arabic

    def test_thai_text_in_messages(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        thai = "สวัสดีครับ วันนี้เป็นอย่างไรบ้าง?"
        message_model.save(conn["connection_id"], 1001, thai, "Hello!")
        msgs = message_model.get_recent(conn["connection_id"])
        assert msgs[0]["original_text"] == thai

    def test_emoji_in_messages(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        emoji_text = "Great job! 🎉👍🐄"
        message_model.save(conn["connection_id"], 1001, emoji_text, "¡Buen trabajo! 🎉👍🐄")
        msgs = message_model.get_recent(conn["connection_id"])
        assert msgs[0]["original_text"] == emoji_text

    def test_mixed_rtl_ltr_in_messages(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        mixed = "הפרה cow 115 צריכה בדיקה"  # Hebrew + English + Hebrew
        message_model.save(conn["connection_id"], 1001, mixed, "translated")
        msgs = message_model.get_recent(conn["connection_id"])
        assert msgs[0]["original_text"] == mixed

    def test_unicode_in_user_name(self, make_user):
        import models.user as user_model
        user = make_user(1001, "אלי", "עברית", "Male")
        assert user["telegram_name"] == "אלי"
        assert user["language"] == "עברית"

    def test_unicode_in_task_description(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        desc = "Check cow 🐄 in field الحقل"
        translated = "בדוק את הפרה 🐄 בשדה"
        tid = task_model.create(conn["connection_id"], desc, translated)
        task = task_model.get_by_id(tid)
        assert task["description"] == desc
        assert task["description_translated"] == translated

    def test_unicode_in_feedback(self):
        import models.feedback as feedback_model
        feedback_model.save(1001, telegram_name="مريم", message="تطبيق رائع! 👏")
        fb = feedback_model.get_all()
        assert fb[0]["telegram_name"] == "مريم"
        assert fb[0]["message"] == "تطبيق رائع! 👏"
