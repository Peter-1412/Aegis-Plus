from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, Relationship, SQLModel


class Role(str, Enum):
    ADMIN = "ADMIN"
    DEVELOPER = "DEVELOPER"
    READONLY = "READONLY"


class UserBase(SQLModel):
    username: str = SQLField(index=True, unique=True, max_length=255)
    role: Role = SQLField(default=Role.DEVELOPER)
    is_active: bool = SQLField(default=False)


class User(UserBase, table=True):
    __tablename__ = "users"
    id: Optional[int] = SQLField(default=None, primary_key=True)
    password_hash: str = SQLField(max_length=255)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = SQLField(default=None)

    # Relationships
    sessions: List["AgentSession"] = Relationship(back_populates="user")
    created_tools: List["OpsTool"] = Relationship(back_populates="created_by")


class OpsToolBase(SQLModel):
    name: str = SQLField(max_length=255)
    type: str = SQLField(max_length=255)
    environment: str = SQLField(max_length=255)
    url: str = SQLField(max_length=1024)
    health_check_url: Optional[str] = SQLField(default=None, max_length=1024)
    description: Optional[str] = SQLField(default=None)
    is_pinned: bool = SQLField(default=False)


class OpsTool(OpsToolBase, table=True):
    __tablename__ = "ops_tools"
    id: Optional[int] = SQLField(default=None, primary_key=True)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    
    created_by_id: Optional[int] = SQLField(default=None, foreign_key="users.id")
    created_by: Optional[User] = Relationship(back_populates="created_tools")


class AgentSessionBase(SQLModel):
    title: str = SQLField(max_length=255)
    is_pinned: bool = SQLField(default=False)


class AgentSession(AgentSessionBase, table=True):
    __tablename__ = "agent_sessions"
    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(foreign_key="users.id")
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))

    user: User = Relationship(back_populates="sessions")
    messages: List["AgentMessage"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class AgentMessage(SQLModel, table=True):
    __tablename__ = "agent_messages"
    id: Optional[int] = SQLField(default=None, primary_key=True)
    session_id: int = SQLField(foreign_key="agent_sessions.id")
    role: str = SQLField(max_length=50)
    content: str
    metadata_json: Optional[str] = SQLField(default=None) # Using metadata_json since metadata is reserved in SQLAlchemy
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))

    session: AgentSession = Relationship(back_populates="messages")


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: Optional[int] = SQLField(default=None, foreign_key="users.id")
    action: str = SQLField(max_length=255)
    resource_type: Optional[str] = SQLField(default=None, max_length=255)
    resource_id: Optional[str] = SQLField(default=None, max_length=255)
    metadata_json: Optional[str] = SQLField(default=None)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
