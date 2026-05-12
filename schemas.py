from pydantic import BaseModel, ConfigDict

class UserBase(BaseModel):
    username: str
    firebase_uid: str | None = None
    email: str | None = None

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int

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
