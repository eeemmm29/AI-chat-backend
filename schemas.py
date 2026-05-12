from pydantic import BaseModel, ConfigDict

class UserCreate(BaseModel):
    username: str

class User(BaseModel):
    id: int
    username: str

    model_config = ConfigDict(from_attributes=True)

class MessageCreate(BaseModel):
    sender: str
    recipient: str
    content: str

class Message(BaseModel):
    id: int
    sender: str
    recipient: str
    content: str
    timestamp: str

    model_config = ConfigDict(from_attributes=True)
