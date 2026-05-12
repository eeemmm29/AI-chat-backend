import asyncio
from unittest.mock import patch

import database
import models
import pytest
import pytest_asyncio
import socketio
import uvicorn
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.fixture(autouse=True)
def setup_db():
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)


@pytest_asyncio.fixture
async def server():
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8080, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.5)
    yield
    server.should_exit = True
    await task


@pytest.mark.asyncio
async def test_socketio_send_message(server):
    sio = socketio.AsyncClient()
    messages = []

    @sio.on("receive_message")
    async def on_receive_message(data):
        messages.append(data)

    mock_user = {"uid": "user1", "email": "user1@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        await sio.connect("http://127.0.0.1:8080", auth={"token": "valid_token"})
        # Emitting 'message' without sender (backend should use session UID)
        await sio.emit(
            "message",
            {
                "recipient": "user2",
                "content": "hello ws",
                "timestamp": "2023-01-01T10:00:00",
            },
        )
        await asyncio.sleep(0.1)

    assert len(messages) == 1
    assert messages[0]["content"] == "hello ws"
    assert messages[0]["sender"] == "user1"  # Verified sender integrity

    db = database.SessionLocal()
    db_messages = db.query(models.Message).all()
    db.close()
    assert len(db_messages) == 1
    assert db_messages[0].content == "hello ws"
    assert db_messages[0].sender == "user1"
    await sio.disconnect()


@pytest.mark.asyncio
async def test_read_users_me_success():
    mock_user = {"uid": "testuser", "email": "test@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(
                "/users/me", headers={"Authorization": "Bearer valid_token"}
            )

    assert response.status_code == 200
    assert response.json() == mock_user


@pytest.mark.asyncio
async def test_read_users_me_no_header():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/users/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid token"


@pytest.mark.asyncio
async def test_read_users_me_invalid_token():
    with patch(
        "firebase_admin.auth.verify_id_token", side_effect=Exception("Invalid token")
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(
                "/users/me", headers={"Authorization": "Bearer invalid_token"}
            )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


@pytest.mark.asyncio
async def test_sync_new_user():
    mock_user = {"uid": "new_uid", "email": "new@example.com", "name": "New User"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/users/sync", headers={"Authorization": "Bearer valid_token"}
            )

    assert response.status_code == 200
    data = response.json()
    assert data["firebase_uid"] == "new_uid"
    assert data["email"] == "new@example.com"
    assert data["username"] == "New User"


@pytest.mark.asyncio
async def test_sync_existing_user_update():
    # First create user
    db = database.SessionLocal()
    user = models.User(
        username="Old Name", firebase_uid="existing_uid", email="old@example.com"
    )
    db.add(user)
    db.commit()
    db.close()

    mock_user = {"uid": "existing_uid", "email": "new@example.com", "name": "New Name"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/users/sync", headers={"Authorization": "Bearer valid_token"}
            )

    assert response.status_code == 200
    data = response.json()
    assert data["firebase_uid"] == "existing_uid"
    assert data["email"] == "new@example.com"
    assert data["username"] == "New Name"


@pytest.mark.asyncio
async def test_get_users():
    db = database.SessionLocal()
    u1 = models.User(username="user1", firebase_uid="uid1")
    u2 = models.User(username="user2", firebase_uid="uid2")
    db.add_all([u1, u2])
    db.commit()
    db.close()

    mock_user = {"uid": "testuser", "email": "test@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            headers = {"Authorization": "Bearer valid_token"}
            response = await ac.get("/users", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    usernames = {u["username"] for u in data}
    assert usernames == {"user1", "user2"}


@pytest.mark.asyncio
async def test_search_users():
    db = database.SessionLocal()
    u1 = models.User(username="alice", firebase_uid="uid_a")
    u2 = models.User(username="bob", firebase_uid="uid_b")
    u3 = models.User(username="charlie", firebase_uid="uid_c")
    db.add_all([u1, u2, u3])
    db.commit()
    db.close()

    mock_user = {"uid": "testuser", "email": "test@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            headers = {"Authorization": "Bearer valid_token"}
            response = await ac.get("/users/search?query=li", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    users = {u["username"] for u in data}
    assert users == {"alice", "charlie"}


@pytest.mark.asyncio
async def test_sync_user_no_email_no_name():
    mock_user = {"uid": "uid_only"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/users/sync", headers={"Authorization": "Bearer valid_token"}
            )

    assert response.status_code == 200
    data = response.json()
    assert data["firebase_uid"] == "uid_only"
    assert data["email"] is None
    assert data["username"] == "user_uid_only"


@pytest.mark.asyncio
async def test_get_messages():
    db = database.SessionLocal()
    m1 = models.Message(
        sender="user1",
        recipient="user2",
        content="hello",
        timestamp="2023-01-01T10:00:00",
    )
    m2 = models.Message(
        sender="user2", recipient="user1", content="hi", timestamp="2023-01-01T10:01:00"
    )
    db.add(m1)
    db.add(m2)
    db.commit()
    db.close()

    mock_user = {"uid": "testuser", "email": "test@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(
                "/messages", headers={"Authorization": "Bearer valid_token"}
            )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["content"] == "hello"
    assert data[1]["content"] == "hi"


@pytest.mark.asyncio
async def test_get_messages_history():
    db = database.SessionLocal()
    m1 = models.Message(
        sender="user1",
        recipient="user2",
        content="hello",
        timestamp="2023-01-01T10:00:00",
    )
    m2 = models.Message(
        sender="user2", recipient="user3", content="hi", timestamp="2023-01-01T10:01:00"
    )
    m3 = models.Message(
        sender="user3",
        recipient="user1",
        content="hey",
        timestamp="2023-01-01T10:02:00",
    )
    db.add_all([m1, m2, m3])
    db.commit()
    db.close()

    mock_user = {"uid": "testuser", "email": "test@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(
                "/messages/history/user1",
                headers={"Authorization": "Bearer valid_token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    contents = {m["content"] for m in data}
    assert contents == {"hello", "hey"}


@pytest.mark.asyncio
async def test_search_messages():
    db = database.SessionLocal()
    m1 = models.Message(
        sender="user1",
        recipient="user2",
        content="hello there",
        timestamp="2023-01-01T10:00:00",
    )
    m2 = models.Message(
        sender="user2",
        recipient="user1",
        content="hi there",
        timestamp="2023-01-01T10:01:00",
    )
    m3 = models.Message(
        sender="user3",
        recipient="user1",
        content="nothing",
        timestamp="2023-01-01T10:02:00",
    )
    db.add_all([m1, m2, m3])
    db.commit()
    db.close()

    mock_user = {"uid": "testuser", "email": "test@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(
                "/messages/search?query=there",
                headers={"Authorization": "Bearer valid_token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    contents = {m["content"] for m in data}
    assert contents == {"hello there", "hi there"}


@pytest.mark.asyncio
async def test_get_messages_conversation():
    db = database.SessionLocal()
    m1 = models.Message(
        sender="user1",
        recipient="user2",
        content="hello",
        timestamp="2023-01-01T10:00:00",
    )
    m2 = models.Message(
        sender="user2", recipient="user1", content="hi", timestamp="2023-01-01T10:01:00"
    )
    m3 = models.Message(
        sender="user1",
        recipient="user3",
        content="hey",
        timestamp="2023-01-01T10:02:00",
    )
    db.add_all([m1, m2, m3])
    db.commit()
    db.close()

    mock_user = {"uid": "testuser", "email": "test@example.com"}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_user):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get(
                "/messages/conversation/user1/user2",
                headers={"Authorization": "Bearer valid_token"},
            )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    contents = {m["content"] for m in data}
    assert contents == {"hello", "hi"}


@pytest.mark.asyncio
async def test_socketio_typing(server):
    sio1 = socketio.AsyncClient()
    sio2 = socketio.AsyncClient()

    events = []

    @sio2.on("typing")
    async def on_typing(data):
        events.append(data)

    mock_user1 = {"uid": "user1", "email": "user1@example.com"}
    mock_user2 = {"uid": "user2", "email": "user2@example.com"}

    with patch("firebase_admin.auth.verify_id_token") as mock_verify:
        mock_verify.side_effect = [mock_user1, mock_user2]
        await sio1.connect("http://127.0.0.1:8080", auth={"token": "token1"})
        await sio2.connect("http://127.0.0.1:8080", auth={"token": "token2"})

    await sio1.emit("typing", {"sender": "user1", "recipient": "user2"})
    await asyncio.sleep(0.1)

    assert len(events) == 1
    assert events[0]["sender"] == "user1"

    await sio1.disconnect()
    await sio2.disconnect()


@pytest.mark.asyncio
async def test_socketio_typing_spoofing(server):
    sio1 = socketio.AsyncClient()
    sio2 = socketio.AsyncClient()

    events = []

    @sio2.on("typing")
    async def on_typing(data):
        events.append(data)

    mock_user1 = {"uid": "real_user1", "email": "user1@example.com"}
    mock_user2 = {"uid": "user2", "email": "user2@example.com"}

    with patch("firebase_admin.auth.verify_id_token") as mock_verify:
        mock_verify.side_effect = [mock_user1, mock_user2]
        await sio1.connect("http://127.0.0.1:8080", auth={"token": "token1"})
        await sio2.connect("http://127.0.0.1:8080", auth={"token": "token2"})

    # User 1 attempts to spoof User 3
    await sio1.emit("typing", {"sender": "spoofed_user3", "recipient": "user2"})
    await asyncio.sleep(0.1)

    assert len(events) == 1
    # This should FAIL initially because the backend currently just broadcasts the raw data
    assert events[0]["sender"] == "real_user1"

    await sio1.disconnect()
    await sio2.disconnect()
