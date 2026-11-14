from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Integer,
    JSON,
    Column,
    Table,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from core.database import Base
from core.ids import id_server_default
from typing import Optional, List


role_permissions_table = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_roles_table = Table(
    "users_roles",
    Base.metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    roles: Mapped[list["Roles"]] = relationship(
        "Roles", secondary=user_roles_table, back_populates="users", lazy="selectin"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise"
    )
    sessions: Mapped[List["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def permissions(self) -> set[str]:
        """Computed on access, not stored in the database. Always reflects the current role assignments."""
        return {perm.name for role in self.roles for perm in role.permissions}


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("uq_conversations_user_idem", "user_id", "idempotency_key", unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(100), default="New Conversation"
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    # Client-supplied Idempotency-Key; null never collides.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index(
            "uq_messages_conversation_idem",
            "conversation_id",
            "idempotency_key",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    conversation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    # Display parts (text, sources). Null for messages saved before parts existed.
    parts: Mapped[Optional[list[dict]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    # Set on the user message of a turn sent with an Idempotency-Key.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class LlmUsage(Base):
    """Tokens used by one model call, for the admin usage dashboard."""

    __tablename__ = "llm_usage"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # agent, suggestions, title, summary or other.
    purpose: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Session(Base):
    __tablename__ = "session"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token: Mapped[str] = mapped_column(Text, index=True, unique=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    previous_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rotated_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user: Mapped["User"] = relationship(back_populates="sessions")


class AuditLog(Base):
    """One row per HTTP request. Bodies are never stored, as they hold messages and passwords."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(512))
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    user: Mapped[Optional["User"]] = relationship()


class Roles(Base):
    __tablename__ = "roles"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=id_server_default(),
    )
    name: Mapped[str] = mapped_column(String(20), unique=True)
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions_table,
        back_populates="roles",
        lazy="selectin",
    )
    users: Mapped[list["User"]] = relationship(
        "User", secondary=user_roles_table, back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    name: Mapped[str] = mapped_column(String(100), unique=True)
    resource: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)

    roles: Mapped[list["Roles"]] = relationship(
        "Roles", secondary=role_permissions_table, back_populates="permissions"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    conversation: Mapped["Conversation"] = relationship(back_populates="documents")


class PendingJiraTicket(Base):
    __tablename__ = "pending_jira_tickets"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=id_server_default()
    )
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    jira_key: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )
    approved_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    conversation: Mapped[Optional["Conversation"]] = relationship(
        foreign_keys=[conversation_id]
    )
    approver: Mapped[Optional["User"]] = relationship(foreign_keys=[approved_by])
