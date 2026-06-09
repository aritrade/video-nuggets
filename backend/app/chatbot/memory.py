"""
Conversation session memory management.
Maintains per-session context for follow-up questions.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.database import ChatSession, ChatMessage

MAX_HISTORY_MESSAGES = 20


def get_or_create_session(db: Session, session_id: Optional[str] = None) -> tuple[str, list[dict]]:
    """Get existing session history or create a new session."""
    if session_id:
        session = db.query(ChatSession).filter(
            ChatSession.session_id == session_id
        ).first()
        if session:
            session.last_active = datetime.utcnow()
            db.commit()
            messages = db.query(ChatMessage).filter(
                ChatMessage.session_id == session.id
            ).order_by(ChatMessage.created_at.desc()).limit(MAX_HISTORY_MESSAGES).all()
            messages.reverse()
            history = [{"role": m.role, "content": m.content} for m in messages]
            return session_id, history

    new_session_id = str(uuid.uuid4())[:16]
    session = ChatSession(session_id=new_session_id)
    db.add(session)
    db.commit()
    return new_session_id, []


def save_message(db: Session, session_id: str, role: str, content: str, cited_videos: str = None):
    """Save a message to the session history."""
    session = db.query(ChatSession).filter(
        ChatSession.session_id == session_id
    ).first()
    if not session:
        return

    message = ChatMessage(
        session_id=session.id,
        role=role,
        content=content,
        cited_videos=cited_videos,
    )
    db.add(message)
    db.commit()
