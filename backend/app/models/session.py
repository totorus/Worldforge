import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WizardSession(Base):
    __tablename__ = "wizard_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    world_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("worlds.id"), nullable=True)

    # Conversation history as JSON array of {role, content}
    messages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Current wizard step (1-11)
    current_step: Mapped[int | None] = mapped_column(default=1)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    # Status: active | finalized | abandoned

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
