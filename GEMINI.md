# Backend Architecture & API Definitions

This directory contains the Python FastAPI backend.
**Tech Stack**: FastAPI, PostgreSQL, Socket.io (via python-socketio).

## API Endpoints

### User Management
- `POST /users/register`: Register a new user (`{"username": "string"}`).
- `GET /users`: List all users.
- `GET /users/search?query=...`: Search users by username.

### Messaging
- `GET /messages`: Retrieve all messages.
- `GET /messages/history/{user_id}`: Retrieve chat history for a specific conversation.
- `GET /messages/search?query=...`: Search messages by content.

## Socket.io Events

- `connect` / `disconnect`: Handle client connections.
- `send_message`: Client sends a message. Payload: `{"sender": "string", "recipient": "string", "content": "string"}`.
- `receive_message`: Server pushes a message to clients. Payload: `{"sender": "string", "content": "string", "timestamp": "string"}`.
- `typing`: Typing indicator. Payload: `{"sender": "string", "recipient": "string", "is_typing": boolean}`.

## Database
- Using **PostgreSQL** as the source of truth.
- Define models for User and Message.