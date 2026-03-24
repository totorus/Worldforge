import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class World(Base):
    __tablename__ = "worlds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    # Status: draft | configured | simulated | narrated | published

    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timeline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    narrative_blocks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    bookstack_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    simulation_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_events: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_factions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
