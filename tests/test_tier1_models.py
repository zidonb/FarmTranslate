"""
Tier 1: Model layer tests — pure database operations.

Tests every model module (user, manager, worker, connection, message, task,
subscription, usage, feedback) against a real PostgreSQL test database.

Each test is independent thanks to the autouse clean_tables fixture
that truncates all tables between tests.
"""
import pytest
from datetime import datetime, timedelta, timezone


# ====================================================================
# USER MODEL
# ====================================================================

class TestUserModel:
    """models.user — identity layer CRUD."""

    def test_create_and_get(self, make_user):
        user = make_user(1001, "Alice", "English", "Female")
        assert user["user_id"] == 1001
        assert user["telegram_name"] == "Alice"
        assert user["language"] == "English"
        assert user["gender"] == "Female"
        assert user["created_at"] is not None

    def test_get_nonexistent_returns_none(self):
        import models.user as user_model
        assert user_model.get_by_id(999999) is None

    def test_create_upserts_on_conflict(self, make_user):
        import models.user as user_model
        make_user(1001, "Alice", "English", "Female")
        user_model.create(1001, telegram_name="Alice2", language="Español", gender="Male")
        user = user_model.get_by_id(1001)
        assert user["telegram_name"] == "Alice2"
        assert user["language"] == "Español"
        assert user["gender"] == "Male"

    def test_update_partial_fields(self, make_user):
        import models.user as user_model
        make_user(1001, "Alice", "English", "Female")
        user_model.update(1001, language="Français")
        user = user_model.get_by_id(1001)
        assert user["language"] == "Français"
        assert user["telegram_name"] == "Alice"
        assert user["gender"] == "Female"

    def test_update_ignores_disallowed_fields(self, make_user):
        import models.user as user_model
        make_user(1001, "Alice", "English", "Female")
        user_model.update(1001, created_at="2000-01-01", language="Deutsch")
        user = user_model.get_by_id(1001)
        assert user["user_id"] == 1001
        assert user["language"] == "Deutsch"

    def test_delete(self, make_user):
        import models.user as user_model
        make_user(1001, "Alice")
        user_model.delete(1001)
        assert user_model.get_by_id(1001) is None

    def test_get_all(self, make_user):
        import models.user as user_model
        make_user(1001, "Alice")
        make_user(1002, "Bob")
        all_users = user_model.get_all()
        assert len(all_users) == 2
        assert all_users[0]["user_id"] == 1002  # newest first


# ====================================================================
# MANAGER MODEL
# ====================================================================

class TestManagerModel:

    def test_create_and_get(self, make_manager):
        _, mgr = make_manager(1001, code="BRIDGE-11111", industry="dairy_farm")
        assert mgr["manager_id"] == 1001
        assert mgr["code"] == "BRIDGE-11111"
        assert mgr["industry"] == "dairy_farm"

    def test_get_by_code(self, make_manager):
        import models.manager as manager_model
        make_manager(1001, code="BRIDGE-22222")
        assert manager_model.get_by_code("BRIDGE-22222")["manager_id"] == 1001

    def test_get_by_code_not_found(self):
        import models.manager as manager_model
        assert manager_model.get_by_code("BRIDGE-99999") is None

    def test_soft_delete_hides(self, make_manager):
        import models.manager as manager_model
        make_manager(1001, code="BRIDGE-33333")
        manager_model.soft_delete(1001)
        assert manager_model.get_by_id(1001) is None
        assert manager_model.get_by_code("BRIDGE-33333") is None

    def test_code_exists(self, make_manager):
        import models.manager as manager_model
        make_manager(1001, code="BRIDGE-44444")
        assert manager_model.code_exists("BRIDGE-44444") is True
        assert manager_model.code_exists("BRIDGE-00000") is False

    def test_code_freed_after_soft_delete(self, make_manager):
        import models.manager as manager_model
        make_manager(1001, code="BRIDGE-55555")
        manager_model.soft_delete(1001)
        assert manager_model.code_exists("BRIDGE-55555") is False

    def test_get_role_manager(self, make_manager):
        import models.manager as manager_model
        make_manager(1001)
        assert manager_model.get_role(1001) == "manager"

    def test_get_role_worker(self, make_worker):
        import models.manager as manager_model
        make_worker(2001)
        assert manager_model.get_role(2001) == "worker"

    def test_get_role_unregistered(self):
        import models.manager as manager_model
        assert manager_model.get_role(9999) is None

    def test_get_all_active(self, make_manager):
        import models.manager as manager_model
        make_manager(1001, code="BRIDGE-10001")
        make_manager(1002, name="Manager2", code="BRIDGE-10002")
        assert len(manager_model.get_all_active()) == 2

    def test_unique_code_constraint(self, make_manager):
        import models.manager as manager_model
        import models.user as user_model
        make_manager(1001, code="BRIDGE-10001")
        user_model.create(1002, "Other")
        with pytest.raises(Exception):
            manager_model.create(1002, "BRIDGE-10001", "other")


# ====================================================================
# WORKER MODEL
# ====================================================================

class TestWorkerModel:

    def test_create_and_get(self, make_worker):
        _, wrk = make_worker(2001)
        assert wrk["worker_id"] == 2001

    def test_soft_delete(self, make_worker):
        import models.worker as worker_model
        make_worker(2001)
        worker_model.soft_delete(2001)
        assert worker_model.get_by_id(2001) is None

    def test_re_create_after_soft_delete(self, make_worker):
        import models.worker as worker_model
        make_worker(2001)
        worker_model.soft_delete(2001)
        worker_model.create(2001)
        assert worker_model.get_by_id(2001) is not None

    def test_get_all_active_with_connection(self, make_connection):
        """Dashboard needs workers with connection info."""
        import models.worker as worker_model
        make_connection(1001, 2001, bot_slot=1)
        all_w = worker_model.get_all_active()
        assert len(all_w) == 1
        assert all_w[0]["worker_id"] == 2001
        assert all_w[0]["manager_id"] == 1001
        assert all_w[0]["bot_slot"] == 1

    def test_get_all_active_unconnected(self, make_worker):
        """Unconnected worker has NULL manager_id and bot_slot."""
        import models.worker as worker_model
        make_worker(2001)
        all_w = worker_model.get_all_active()
        assert len(all_w) == 1
        assert all_w[0]["manager_id"] is None


# ====================================================================
# CONNECTION MODEL
# ====================================================================

class TestConnectionModel:

    def test_create_and_get(self, make_connection):
        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        assert conn["manager_id"] == 1001
        assert conn["worker_id"] == 2001
        assert conn["bot_slot"] == 1
        assert conn["status"] == "active"

    def test_duplicate_slot(self, make_connection, make_worker):
        from models.connection import SlotOccupiedError
        import models.connection as connection_model
        make_connection(1001, 2001, bot_slot=1)
        make_worker(2002, "Worker2", "Français")
        with pytest.raises(SlotOccupiedError):
            connection_model.create(1001, 2002, bot_slot=1)

    def test_worker_already_connected(self, make_connection, make_manager):
        from models.connection import WorkerAlreadyConnectedError
        import models.connection as connection_model
        make_connection(1001, 2001, bot_slot=1)
        make_manager(1002, "Manager2", code="BRIDGE-20002")
        with pytest.raises(WorkerAlreadyConnectedError):
            connection_model.create(1002, 2001, bot_slot=1)

    def test_multi_slot(self, make_manager, make_worker):
        import models.connection as connection_model
        make_manager(1001, code="BRIDGE-10001")
        for slot, wid in [(1, 2001), (2, 2002), (3, 2003)]:
            make_worker(wid, f"Worker{wid}", "Español")
            connection_model.create(1001, wid, slot)
        assert len(connection_model.get_active_for_manager(1001)) == 3

    def test_disconnect_and_reconnect(self, make_connection, make_worker):
        import models.connection as connection_model
        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        connection_model.disconnect(conn["connection_id"])
        assert connection_model.get_by_manager_and_slot(1001, 1) is None
        make_worker(2002, "Worker2", "Français")
        new_id = connection_model.create(1001, 2002, bot_slot=1)
        assert connection_model.get_by_id(new_id)["worker_id"] == 2002

    def test_disconnect_idempotent(self, make_connection):
        import models.connection as connection_model
        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        connection_model.disconnect(conn["connection_id"])
        assert connection_model.disconnect(conn["connection_id"]) is None

    def test_get_active_for_worker(self, make_connection):
        import models.connection as connection_model
        make_connection(1001, 2001, bot_slot=1)
        assert connection_model.get_active_for_worker(2001)["manager_id"] == 1001

    def test_get_all_active_has_names(self, make_connection):
        import models.connection as connection_model
        make_connection(1001, 2001, bot_slot=1)
        all_c = connection_model.get_all_active()
        assert len(all_c) == 1
        assert "manager_name" in all_c[0]
        assert "worker_name" in all_c[0]


# ====================================================================
# MESSAGE MODEL
# ====================================================================

class TestMessageModel:

    def test_save_and_get_recent(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        message_model.save(conn["connection_id"], 1001, "Hello", "Hola")
        msgs = message_model.get_recent(conn["connection_id"], hours=1)
        assert len(msgs) == 1
        assert msgs[0]["original_text"] == "Hello"

    def test_translation_context_chronological(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        cid = conn["connection_id"]
        for i in range(5):
            message_model.save(cid, 1001, f"msg{i}", f"t{i}")
        ctx = message_model.get_translation_context(cid, limit=3)
        assert len(ctx) == 3
        assert ctx[0]["text"] == "msg2"
        assert ctx[2]["text"] == "msg4"

    def test_get_count(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        cid = conn["connection_id"]
        message_model.save(cid, 1001, "a", "b")
        message_model.save(cid, 2001, "c", "d")
        assert message_model.get_count(cid) == 2

    def test_cleanup_expired(self, make_connection):
        import models.message as message_model
        from utils.db_connection import get_db_cursor
        _, _, conn = make_connection(1001, 2001)
        cid = conn["connection_id"]
        message_model.save(cid, 1001, "old", "viejo")
        with get_db_cursor() as cur:
            cur.execute("UPDATE messages SET sent_at = NOW() - INTERVAL '60 days' WHERE connection_id = %s", (cid,))
        message_model.cleanup_expired()
        assert message_model.get_count(cid) == 0

    def test_backward_compat_keys(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        message_model.save(conn["connection_id"], 1001, "Hello", "Hola")
        msgs = message_model.get_recent(conn["connection_id"])
        assert msgs[0]["from"] == "1001"
        assert msgs[0]["text"] == "Hello"

    # --- Dashboard-required methods ---

    def test_get_for_connection(self, make_connection):
        """All messages for a connection, chronological."""
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        cid = conn["connection_id"]
        message_model.save(cid, 1001, "First", "Primero")
        message_model.save(cid, 2001, "Second", "Segundo")
        msgs = message_model.get_for_connection(cid)
        assert len(msgs) == 2
        assert msgs[0]["original_text"] == "First"
        assert msgs[1]["sender_id"] == 2001

    def test_get_total_count(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        message_model.save(conn["connection_id"], 1001, "a", "b")
        message_model.save(conn["connection_id"], 2001, "c", "d")
        assert message_model.get_total_count() == 2

    def test_get_total_count_empty(self):
        import models.message as message_model
        assert message_model.get_total_count() == 0

    def test_delete_for_connection(self, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001)
        cid = conn["connection_id"]
        message_model.save(cid, 1001, "a", "b")
        message_model.save(cid, 2001, "c", "d")
        message_model.delete_for_connection(cid)
        assert message_model.get_count(cid) == 0

    def test_get_recent_across_connections(self, make_connection, make_worker):
        """Grouped conversations for dashboard."""
        import models.message as message_model
        import models.connection as connection_model
        _, _, conn1 = make_connection(1001, 2001, bot_slot=1)
        message_model.save(conn1["connection_id"], 1001, "Hi w1", "Hola")
        make_worker(2002, "Worker2", "Français")
        cid2 = connection_model.create(1001, 2002, bot_slot=2)
        message_model.save(cid2, 1001, "Hi w2", "Bonjour")
        convs = message_model.get_recent_across_connections(limit_per_connection=10)
        assert len(convs) == 2
        for conv in convs:
            assert "connection_id" in conv
            assert "manager_name" in conv
            assert len(conv["messages"]) >= 1


# ====================================================================
# TASK MODEL
# ====================================================================

class TestTaskModel:

    def test_create_and_get(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        tid = task_model.create(conn["connection_id"], "Check cow 115", "Revisar vaca 115")
        task = task_model.get_by_id(tid)
        assert task["description"] == "Check cow 115"
        assert task["status"] == "pending"

    def test_complete(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        tid = task_model.create(conn["connection_id"], "Fix gate")
        result = task_model.complete(tid)
        assert result is not None
        assert task_model.get_by_id(tid)["status"] == "completed"

    def test_complete_idempotent(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        tid = task_model.create(conn["connection_id"], "Fix gate")
        task_model.complete(tid)
        assert task_model.complete(tid) is None

    def test_get_manager_tasks(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        task_model.create(conn["connection_id"], "A")
        task_model.create(conn["connection_id"], "B")
        assert len(task_model.get_manager_tasks(1001)) == 2

    def test_filter_by_status(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        t1 = task_model.create(conn["connection_id"], "A")
        task_model.create(conn["connection_id"], "B")
        task_model.complete(t1)
        assert len(task_model.get_manager_tasks(1001, status="pending")) == 1

    def test_worker_tasks_translated(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        task_model.create(conn["connection_id"], "Check cow", "Revisar vaca")
        tasks = task_model.get_worker_tasks(2001)
        assert tasks[0]["description"] == "Revisar vaca"

    def test_stats(self, make_connection):
        import models.task as task_model
        _, _, conn = make_connection(1001, 2001)
        t1 = task_model.create(conn["connection_id"], "A")
        task_model.create(conn["connection_id"], "B")
        task_model.complete(t1)
        stats = task_model.get_stats(1001)
        assert stats["total"] == 2
        assert stats["pending"] == 1
        assert stats["completed"] == 1


# ====================================================================
# SUBSCRIPTION MODEL
# ====================================================================

class TestSubscriptionModel:

    def test_save_and_get(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, external_id="ext_123", status="active",
                       customer_portal_url="https://portal.example.com")
        sub = sub_model.get_by_manager(1001)
        assert sub["status"] == "active"
        assert sub["external_id"] == "ext_123"

    def test_is_active_true(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active")
        assert sub_model.is_active(1001) is True

    def test_is_active_false_no_sub(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        assert sub_model.is_active(1001) is False

    def test_cancelled_not_expired_still_active(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        future = datetime.now(timezone.utc) + timedelta(days=15)
        sub_model.save(1001, status="cancelled", ends_at=future)
        assert sub_model.is_active(1001) is True

    def test_cancelled_and_expired_inactive(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        sub_model.save(1001, status="cancelled", ends_at=past)
        assert sub_model.is_active(1001) is False

    def test_expired_status_inactive(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="expired")
        assert sub_model.is_active(1001) is False

    def test_update_status(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active")
        sub_model.update_status(1001, "cancelled",
                                ends_at=datetime.now(timezone.utc) + timedelta(days=10))
        assert sub_model.get_by_manager(1001)["status"] == "cancelled"

    def test_upsert(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active", external_id="ext_1")
        sub_model.save(1001, status="cancelled", external_id="ext_2")
        sub = sub_model.get_by_manager(1001)
        assert sub["status"] == "cancelled"
        assert sub["external_id"] == "ext_2"

    def test_delete(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active")
        sub_model.delete(1001)
        assert sub_model.get_by_manager(1001) is None

    def test_checkout_url(self, make_manager):
        import models.subscription as sub_model
        url = sub_model.create_checkout_url(1001)
        assert "telegram_id]=1001" in url or "telegram_id=1001" in url

    def test_get_all(self, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        make_manager(1002, name="M2", code="BRIDGE-10002")
        sub_model.save(1001, status="active")
        sub_model.save(1002, status="cancelled")
        assert len(sub_model.get_all()) == 2


# ====================================================================
# USAGE MODEL
# ====================================================================

class TestUsageModel:

    def test_increment_allows_first(self, make_manager):
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        assert usage_model.increment(1001) is True

    def test_blocks_at_limit(self, make_manager):
        """free_message_limit=3 → message 3 triggers block."""
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        assert usage_model.increment(1001) is True   # 1
        assert usage_model.increment(1001) is True   # 2
        assert usage_model.increment(1001) is False   # 3 = limit
        assert usage_model.increment(1001) is False   # 4

    def test_is_blocked(self, make_manager):
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        assert usage_model.is_blocked(1001) is False
        for _ in range(3):
            usage_model.increment(1001)
        assert usage_model.is_blocked(1001) is True

    def test_reset(self, make_manager):
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        for _ in range(3):
            usage_model.increment(1001)
        usage_model.reset(1001)
        u = usage_model.get(1001)
        assert u["messages_sent"] == 0
        assert u["is_blocked"] is False

    def test_block_explicit(self, make_manager):
        """block() used by webhook when subscription expires and user was over limit."""
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        usage_model.increment(1001)  # Ensure row exists
        usage_model.block(1001)
        assert usage_model.is_blocked(1001) is True

    def test_unblock_preserves_counter(self, make_manager):
        """unblock() clears blocked flag but keeps messages_sent intact."""
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        for _ in range(3):
            usage_model.increment(1001)
        usage_model.unblock(1001)
        assert usage_model.is_blocked(1001) is False
        assert usage_model.get(1001)["messages_sent"] == 3

    def test_get_none_for_no_record(self):
        import models.usage as usage_model
        assert usage_model.get(9999) is None

    def test_get_all(self, make_manager):
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        usage_model.increment(1001)
        assert len(usage_model.get_all()) == 1

    def test_get_stats(self, make_manager):
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        for _ in range(3):
            usage_model.increment(1001)
        stats = usage_model.get_stats()
        assert stats["total_users_tracked"] == 1
        assert stats["blocked_users"] == 1


# ====================================================================
# FEEDBACK MODEL
# ====================================================================

class TestFeedbackModel:

    def test_save_and_get_all(self):
        import models.feedback as feedback_model
        feedback_model.save(1001, telegram_name="Alice", username="alice",
                            message="Great app!")
        fb = feedback_model.get_all()
        assert len(fb) == 1
        assert fb[0]["message"] == "Great app!"
        assert fb[0]["status"] == "unread"

    def test_mark_as_read(self):
        import models.feedback as feedback_model
        feedback_model.save(1001, message="Bug")
        fb_id = feedback_model.get_all()[0]["feedback_id"]
        feedback_model.mark_as_read(fb_id)
        assert feedback_model.get_all()[0]["status"] == "read"

    def test_ordered_newest_first(self):
        import models.feedback as feedback_model
        feedback_model.save(1001, message="First")
        feedback_model.save(1002, message="Second")
        assert feedback_model.get_all()[0]["message"] == "Second"

    def test_limit(self):
        import models.feedback as feedback_model
        for i in range(10):
            feedback_model.save(1000 + i, message=f"msg{i}")
        assert len(feedback_model.get_all(limit=5)) == 5
