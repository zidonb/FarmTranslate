"""
Tier 4: Dashboard route tests — actual Flask routes with real DB.

Now that dashboard.py uses models.* imports, we can test the actual
dashboard routes with Flask's test client:
  - Auth protection (login/logout)
  - CSRF enforcement on POST actions
  - Main dashboard renders with data
  - Manager detail page
  - Admin actions (delete user, reset usage, clear history, mark feedback)
  - Health check
"""
import pytest
import json


# ====================================================================
# FIXTURES
# ====================================================================

@pytest.fixture
def app():
    """Import and configure the real dashboard app."""
    import importlib
    import dashboard as dashboard_mod
    importlib.reload(dashboard_mod)
    dashboard_mod.app.config["TESTING"] = True
    # Patch send_telegram_notification to not make real HTTP calls
    dashboard_mod.send_telegram_notification = lambda *a, **kw: None
    return dashboard_mod.app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, password="test_password"):
    return client.post("/login", data={"password": password}, follow_redirects=True)


def get_csrf(client):
    """Get a CSRF token from the session."""
    with client.session_transaction() as sess:
        import secrets
        token = secrets.token_hex(32)
        sess["csrf_token"] = token
    return token


# ====================================================================
# AUTH
# ====================================================================

class TestAuth:

    def test_dashboard_requires_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_login_success(self, client):
        resp = login(client)
        assert resp.status_code == 200

    def test_login_wrong_password(self, client):
        resp = client.post("/login", data={"password": "wrong"})
        assert b"Invalid password" in resp.data

    def test_logout(self, client):
        login(client)
        client.get("/logout")
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302

    def test_manager_detail_requires_login(self, client):
        resp = client.get("/manager/1001", follow_redirects=False)
        assert resp.status_code == 302


# ====================================================================
# CSRF
# ====================================================================

class TestCSRF:

    def test_post_without_csrf(self, client, make_manager):
        login(client)
        make_manager(1001, code="BRIDGE-10001")
        resp = client.post("/reset_usage/1001", data={})
        assert resp.status_code == 403

    def test_post_with_valid_csrf(self, client, make_manager):
        import models.usage as usage_model
        login(client)
        make_manager(1001, code="BRIDGE-10001")
        usage_model.increment(1001)
        token = get_csrf(client)
        resp = client.post("/reset_usage/1001", data={"csrf_token": token},
                           follow_redirects=True)
        assert resp.status_code == 200


# ====================================================================
# HEALTH CHECK
# ====================================================================

class TestHealthCheck:

    def test_health_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert json.loads(resp.data)["status"] == "healthy"


# ====================================================================
# DASHBOARD MAIN PAGE
# ====================================================================

class TestDashboardPage:

    def test_renders_empty(self, client):
        """Dashboard renders with no data."""
        login(client)
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"BridgeOS Dashboard" in resp.data

    def test_renders_with_data(self, client, make_connection):
        """Dashboard renders with managers, workers, connections."""
        import models.message as message_model
        import models.feedback as feedback_model
        import models.subscription as sub_model

        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        message_model.save(conn["connection_id"], 1001, "Hello", "Hola")
        sub_model.save(1001, status="active")
        feedback_model.save(1001, telegram_name="Alice", message="Great!")

        login(client)
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"BridgeOS Dashboard" in resp.data


# ====================================================================
# MANAGER DETAIL PAGE
# ====================================================================

class TestManagerDetail:

    def test_renders_for_valid_manager(self, client, make_connection):
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        message_model.save(conn["connection_id"], 1001, "Test msg", "Msg prueba")

        login(client)
        resp = client.get("/manager/1001")
        assert resp.status_code == 200
        assert b"Manager Details" in resp.data

    def test_redirects_for_nonexistent_manager(self, client):
        login(client)
        resp = client.get("/manager/9999", follow_redirects=False)
        assert resp.status_code == 302

    def test_redirects_for_worker_id(self, client, make_worker):
        """Trying to view a worker as a manager detail → redirect."""
        make_worker(2001)
        login(client)
        resp = client.get("/manager/2001", follow_redirects=False)
        assert resp.status_code == 302


# ====================================================================
# ADMIN ACTIONS
# ====================================================================

class TestAdminActions:

    def test_delete_manager(self, client, make_connection):
        """Deleting a manager disconnects workers and removes user."""
        import models.user as user_model
        import models.connection as connection_model
        make_connection(1001, 2001, bot_slot=1)

        login(client)
        token = get_csrf(client)
        resp = client.post("/delete_user/1001", data={"csrf_token": token},
                           follow_redirects=True)
        assert resp.status_code == 200
        assert user_model.get_by_id(1001) is None
        assert len(connection_model.get_active_for_manager(1001)) == 0

    def test_delete_worker(self, client, make_connection):
        """Deleting a worker disconnects and removes user."""
        import models.user as user_model
        import models.connection as connection_model
        make_connection(1001, 2001, bot_slot=1)

        login(client)
        token = get_csrf(client)
        resp = client.post("/delete_user/2001", data={"csrf_token": token},
                           follow_redirects=True)
        assert resp.status_code == 200
        assert user_model.get_by_id(2001) is None
        assert connection_model.get_active_for_worker(2001) is None

    def test_delete_nonexistent_user(self, client):
        """Deleting a non-existent user just redirects."""
        login(client)
        token = get_csrf(client)
        resp = client.post("/delete_user/9999", data={"csrf_token": token},
                           follow_redirects=False)
        assert resp.status_code == 302

    def test_reset_usage(self, client, make_manager):
        """Reset usage clears counter and unblocks."""
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        for _ in range(5):
            usage_model.increment(1001)

        login(client)
        token = get_csrf(client)
        resp = client.post("/reset_usage/1001", data={"csrf_token": token},
                           follow_redirects=True)
        assert resp.status_code == 200
        usage = usage_model.get(1001)
        assert usage["messages_sent"] == 0
        assert usage["is_blocked"] is False

    def test_clear_conversation(self, client, make_connection):
        """Clear conversation deletes all messages for a connection."""
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        cid = conn["connection_id"]
        message_model.save(cid, 1001, "Hello", "Hola")
        message_model.save(cid, 2001, "Hi", "Hola")

        login(client)
        token = get_csrf(client)
        resp = client.post(f"/clear_conversation/{cid}",
                           data={"csrf_token": token}, follow_redirects=True)
        assert resp.status_code == 200
        assert message_model.get_count(cid) == 0

    def test_clear_translation_context(self, client, make_connection):
        """Clear translation context for a specific connection."""
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        cid = conn["connection_id"]
        message_model.save(cid, 1001, "a", "b")

        login(client)
        token = get_csrf(client)
        resp = client.post(f"/clear_translation_context/1001/{cid}",
                           data={"csrf_token": token}, follow_redirects=True)
        assert resp.status_code == 200
        assert message_model.get_count(cid) == 0

    def test_clear_full_history(self, client, make_connection):
        """Clear full history for a specific connection."""
        import models.message as message_model
        _, _, conn = make_connection(1001, 2001, bot_slot=1)
        cid = conn["connection_id"]
        message_model.save(cid, 1001, "msg1", "t1")
        message_model.save(cid, 2001, "msg2", "t2")

        login(client)
        token = get_csrf(client)
        resp = client.post(f"/clear_full_history/1001/{cid}",
                           data={"csrf_token": token}, follow_redirects=True)
        assert resp.status_code == 200
        assert message_model.get_count(cid) == 0

    def test_mark_feedback_read(self, client):
        """Mark feedback as read via admin action."""
        import models.feedback as feedback_model
        feedback_model.save(1001, telegram_name="Alice", message="Bug!")
        fb_id = feedback_model.get_all()[0]["feedback_id"]

        login(client)
        token = get_csrf(client)
        resp = client.post(f"/mark_feedback_read/{fb_id}",
                           data={"csrf_token": token}, follow_redirects=True)
        assert resp.status_code == 200
        assert feedback_model.get_all()[0]["status"] == "read"

    def test_admin_actions_require_auth(self, client, make_manager):
        """All admin POST routes redirect to login without auth."""
        make_manager(1001, code="BRIDGE-10001")
        routes = [
            "/delete_user/1001",
            "/reset_usage/1001",
            "/clear_conversation/1",
            "/clear_translation_context/1001/1",
            "/clear_full_history/1001/1",
            "/mark_feedback_read/1",
        ]
        for route in routes:
            resp = client.post(route, data={"csrf_token": "x"}, follow_redirects=False)
            assert resp.status_code == 302, f"{route} should require auth"
            assert "/login" in resp.headers["Location"]
