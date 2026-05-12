import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from main import app
import models, database
import asyncio
import uvicorn
import socketio

@pytest.fixture(autouse=True)
def setup_db():
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)

@pytest_asyncio.fixture
async def server():
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, log_level="error")
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
    
    @sio.on('receive_message')
    async def on_receive_message(data):
        messages.append(data)
        
    await sio.connect('http://127.0.0.1:8000')
    await sio.emit('send_message', {'sender': 'user1', 'recipient': 'user2', 'content': 'hello ws', 'timestamp': '2023-01-01T10:00:00'})
    await asyncio.sleep(0.1)
    
    assert len(messages) == 1
    assert messages[0]['content'] == 'hello ws'
    
    db = database.SessionLocal()
    db_messages = db.query(models.Message).all()
    db.close()
    assert len(db_messages) == 1
    assert db_messages[0].content == 'hello ws'
    await sio.disconnect()

@pytest.mark.asyncio
async def test_register_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/users/register", json={"username": "testuser"})
    assert response.status_code == 200
    assert response.json() == {"id": 1, "username": "testuser"}

@pytest.mark.asyncio
async def test_get_users():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/users/register", json={"username": "user1"})
        await ac.post("/users/register", json={"username": "user2"})
        
        response = await ac.get("/users")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["username"] == "user1"
    assert data[1]["username"] == "user2"

@pytest.mark.asyncio
async def test_search_users():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/users/register", json={"username": "alice"})
        await ac.post("/users/register", json={"username": "bob"})
        await ac.post("/users/register", json={"username": "charlie"})
        
        response = await ac.get("/users/search?query=li")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    users = {u["username"] for u in data}
    assert users == {"alice", "charlie"}

@pytest.mark.asyncio
async def test_get_messages():
    db = database.SessionLocal()
    m1 = models.Message(sender="user1", recipient="user2", content="hello", timestamp="2023-01-01T10:00:00")
    m2 = models.Message(sender="user2", recipient="user1", content="hi", timestamp="2023-01-01T10:01:00")
    db.add(m1)
    db.add(m2)
    db.commit()
    db.close()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/messages")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["content"] == "hello"
    assert data[1]["content"] == "hi"

@pytest.mark.asyncio
async def test_get_messages_history():
    db = database.SessionLocal()
    m1 = models.Message(sender="user1", recipient="user2", content="hello", timestamp="2023-01-01T10:00:00")
    m2 = models.Message(sender="user2", recipient="user3", content="hi", timestamp="2023-01-01T10:01:00")
    m3 = models.Message(sender="user3", recipient="user1", content="hey", timestamp="2023-01-01T10:02:00")
    db.add_all([m1, m2, m3])
    db.commit()
    db.close()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/messages/history/user1")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    contents = {m["content"] for m in data}
    assert contents == {"hello", "hey"}

@pytest.mark.asyncio
async def test_search_messages():
    db = database.SessionLocal()
    m1 = models.Message(sender="user1", recipient="user2", content="hello there", timestamp="2023-01-01T10:00:00")
    m2 = models.Message(sender="user2", recipient="user1", content="hi there", timestamp="2023-01-01T10:01:00")
    m3 = models.Message(sender="user3", recipient="user1", content="nothing", timestamp="2023-01-01T10:02:00")
    db.add_all([m1, m2, m3])
    db.commit()
    db.close()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/messages/search?query=there")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    contents = {m["content"] for m in data}
    assert contents == {"hello there", "hi there"}

@pytest.mark.asyncio
async def test_get_messages_conversation():
    db = database.SessionLocal()
    m1 = models.Message(sender="user1", recipient="user2", content="hello", timestamp="2023-01-01T10:00:00")
    m2 = models.Message(sender="user2", recipient="user1", content="hi", timestamp="2023-01-01T10:01:00")
    m3 = models.Message(sender="user1", recipient="user3", content="hey", timestamp="2023-01-01T10:02:00")
    db.add_all([m1, m2, m3])
    db.commit()
    db.close()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/messages/conversation/user1/user2")
    
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
    @sio2.on('typing')
    async def on_typing(data):
        events.append(data)
        
    await sio1.connect('http://127.0.0.1:8000')
    await sio2.connect('http://127.0.0.1:8000')
    
    await sio1.emit('typing', {'sender': 'user1', 'recipient': 'user2'})
    await asyncio.sleep(0.1)
    
    assert len(events) == 1
    assert events[0]['sender'] == 'user1'
    
    await sio1.disconnect()
    await sio2.disconnect()



