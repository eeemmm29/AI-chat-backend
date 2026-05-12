from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
import models, schemas, database
from typing import List
import asyncio
from pydantic import ValidationError
import socketio
import firebase_admin
from firebase_admin import auth, credentials

models.Base.metadata.create_all(bind=database.engine)

# Initialize Firebase Admin
try:
    firebase_admin.get_app()
except ValueError:
    # Use default credentials or environment variable for production
    firebase_admin.initialize_app()

async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print(f"Error verifying token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

fastapi_app = FastAPI()

@fastapi_app.post("/users/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = models.User(username=user.username)
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username already registered")

@fastapi_app.get("/users", response_model=List[schemas.User])
def get_users(db: Session = Depends(database.get_db)):
    return db.query(models.User).all()

@fastapi_app.get("/users/search", response_model=List[schemas.User])
def search_users(query: str, db: Session = Depends(database.get_db)):
    return db.query(models.User).filter(models.User.username.contains(query)).all()

@fastapi_app.get("/messages", response_model=List[schemas.Message])
def get_messages(db: Session = Depends(database.get_db)):
    return db.query(models.Message).all()

@fastapi_app.get("/messages/history/{user_id}", response_model=List[schemas.Message])
def get_messages_history(user_id: str, db: Session = Depends(database.get_db)):
    return db.query(models.Message).filter(
        or_(models.Message.sender == user_id, models.Message.recipient == user_id)
    ).all()

@fastapi_app.get("/messages/conversation/{user1_id}/{user2_id}", response_model=List[schemas.Message])
def get_messages_conversation(user1_id: str, user2_id: str, db: Session = Depends(database.get_db)):
    return db.query(models.Message).filter(
        or_(
            and_(models.Message.sender == user1_id, models.Message.recipient == user2_id),
            and_(models.Message.sender == user2_id, models.Message.recipient == user1_id)
        )
    ).all()

@fastapi_app.get("/messages/search", response_model=List[schemas.Message])
def search_messages(query: str, db: Session = Depends(database.get_db)):
    return db.query(models.Message).filter(models.Message.content.contains(query)).all()

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@sio.event
async def connect(sid, environ):
    print(f"connect {sid}")

@sio.event
async def disconnect(sid):
    print(f"disconnect {sid}")

@sio.event
async def typing(sid, data):
    await sio.emit('typing', data, skip_sid=sid)

@sio.event
async def send_message(sid, data):
    try:
        msg = schemas.MessageCreate(**data)
    except ValidationError:
        return

    db = database.SessionLocal()
    
    def db_operations():
        try:
            db_message = models.Message(**msg.model_dump())
            db.add(db_message)
            db.commit()
            db.refresh(db_message)
            return db_message
        except Exception:
            db.rollback()
            raise

    try:
        db_message = await asyncio.to_thread(db_operations)
        
        # Emitting receive_message
        await sio.emit('receive_message', {
            'id': db_message.id,
            'sender': db_message.sender,
            'recipient': db_message.recipient,
            'content': db_message.content,
            'timestamp': db_message.timestamp
        })
    finally:
        db.close()

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
