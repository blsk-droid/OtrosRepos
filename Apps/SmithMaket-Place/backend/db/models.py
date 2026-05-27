from datetime import datetime
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy import String, Float, Boolean, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Book(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    docx_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # KDP Book Dimensions (Inches)
    kdp_width_inches: Mapped[float] = mapped_column(Float, default=6.0)
    kdp_height_inches: Mapped[float] = mapped_column(Float, default=9.0)
    
    # Page Margins (Inches)
    margin_inner_inches: Mapped[float] = mapped_column(Float, default=0.75)
    margin_outer_inches: Mapped[float] = mapped_column(Float, default=0.5)
    margin_top_inches: Mapped[float] = mapped_column(Float, default=0.75)
    margin_bottom_inches: Mapped[float] = mapped_column(Float, default=0.75)
    
    # Typesetting Parameters
    font_family: Mapped[str] = mapped_column(String(100), default="Garamond")
    font_size_pt: Mapped[float] = mapped_column(Float, default=11.0)
    line_height_relative: Mapped[float] = mapped_column(Float, default=1.35)  # Leading
    letter_spacing_pt: Mapped[float] = mapped_column(Float, default=0.0)      # Tracking
    
    # Widow and Orphan Control
    widow_orphan_control: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Parsed Content Blocks (JSON representation of DOCX structured blocks)
    # Format: [{"id": "uuid", "text": "...", "style": "Normal", "runs": [{"text": "...", "bold": true}]}]
    content_blocks: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Style Mappings (JSON mapping of block styles to semantic types e.g., Heading 1 -> Chapter Title)
    # Format: {"Heading 1": "chapter_title", "Normal": "body_text"}
    style_mappings: Mapped[Dict[str, str]] = mapped_column(JSON, default=dict)
    
    # Explicit Chapter Definitions (override heuristics)
    # Format: {"chapter_block_ids": ["uuid-1", "uuid-2"]}
    chapter_definitions: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "title": self.title,
            "author": self.author,
            "docx_filename": self.docx_filename,
            "kdp_width_inches": self.kdp_width_inches,
            "kdp_height_inches": self.kdp_height_inches,
            "margin_inner_inches": self.margin_inner_inches,
            "margin_outer_inches": self.margin_outer_inches,
            "margin_top_inches": self.margin_top_inches,
            "margin_bottom_inches": self.margin_bottom_inches,
            "font_family": self.font_family,
            "font_size_pt": self.font_size_pt,
            "line_height_relative": self.line_height_relative,
            "letter_spacing_pt": self.letter_spacing_pt,
            "widow_orphan_control": self.widow_orphan_control,
            "content_blocks": self.content_blocks,
            "style_mappings": self.style_mappings,
            "chapter_definitions": self.chapter_definitions,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
