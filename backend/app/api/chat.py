from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.models.database import get_db
from app.chatbot.llm_service import get_chat_response

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    cited_videos: list[dict] = []
    suggestions: list[str] = []


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    result = await get_chat_response(
        message=request.message,
        session_id=request.session_id,
        db=db,
    )
    return ChatResponse(
        response=result["response"],
        session_id=result["session_id"],
        cited_videos=result.get("cited_videos", []),
        suggestions=result.get("suggestions", []),
    )


@router.delete("/{session_id}")
def clear_session(session_id: str, db: Session = Depends(get_db)):
    from app.models.database import ChatSession, ChatMessage

    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if session:
        db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
        db.delete(session)
        db.commit()
    return {"message": "Session cleared"}
