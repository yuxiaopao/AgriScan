"""Private, persistent conversations for the floating Xiaohe assistant."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow
from .security import current_user


class Conversation(Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(80), default="新对话")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    busy_until: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime(2000, 1, 1))


class ChatMessage(Base):
    __tablename__ = "assistant_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("assistant_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChatInput(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


def conversation_data(row):
    return {"id": row.id, "title": row.title,
            "updated_at": row.updated_at.replace(tzinfo=timezone.utc).isoformat()}


def message_data(row):
    return {"id": row.id, "role": row.role, "content": row.content,
            "created_at": row.created_at.replace(tzinfo=timezone.utc).isoformat()}


def install_assistant(app, get_db, answer_for):
    def owned(db, conversation_id, user):
        row = db.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id))
        if not row:
            raise HTTPException(404, "对话不存在。")
        return row

    @app.get("/api/assistant/conversations")
    def conversations(user=Depends(current_user), db=Depends(get_db)):
        rows = db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                          .order_by(Conversation.updated_at.desc()).limit(100)).all()
        return [conversation_data(row) for row in rows]

    @app.post("/api/assistant/conversations", status_code=201)
    def create(user=Depends(current_user), db=Depends(get_db)):
        row = Conversation(user_id=user.id)
        db.add(row)
        db.commit()
        return conversation_data(row)

    @app.get("/api/assistant/conversations/{conversation_id}")
    def detail(conversation_id: str, user=Depends(current_user), db=Depends(get_db)):
        row = owned(db, conversation_id, user)
        messages = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == row.id)
                             .order_by(ChatMessage.id)).all()
        return {"conversation": conversation_data(row), "messages": [message_data(m) for m in messages]}

    @app.post("/api/assistant/conversations/{conversation_id}/messages")
    def send(conversation_id: str, body: ChatInput, user=Depends(current_user), db=Depends(get_db)):
        row = owned(db, conversation_id, user)
        question = body.question.strip()
        if len(question) < 2:
            raise HTTPException(422, "请输入至少两个字符的问题。")
        # A DB lease prevents overlapping requests even across API processes.
        now = utcnow().replace(microsecond=0)
        lease = now + timedelta(seconds=150)
        acquired = db.execute(update(Conversation).where(
            Conversation.id == row.id, Conversation.busy_until < now
        ).values(busy_until=lease))
        db.commit()
        if not acquired.rowcount:
            raise HTTPException(409, "小禾正在回复这段对话，请稍后再发送。")
        try:
            count = db.scalar(select(func.count()).select_from(ChatMessage)
                              .where(ChatMessage.conversation_id == row.id))
            if count >= 200:
                raise HTTPException(409, "这段对话已满，请新建对话继续交流。")
            recent = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == row.id)
                               .order_by(ChatMessage.id.desc()).limit(20)).all()
            context = [{"role": m.role, "content": m.content} for m in reversed(recent)]
            while len(context) > 2 and sum(len(m["content"]) for m in context) > 24000:
                context = context[2:]
            answer = answer_for(user, [*context, {"role": "user", "content": question}])
            messages = [ChatMessage(conversation_id=row.id, role="user", content=question),
                        ChatMessage(conversation_id=row.id, role="assistant", content=answer)]
            db.add_all(messages)
            row.title = question[:40] if count == 0 else row.title
            row.updated_at = utcnow()
            db.commit()
            return {"conversation": conversation_data(row), "messages": [message_data(m) for m in messages]}
        finally:
            db.rollback()
            db.execute(update(Conversation).where(Conversation.id == conversation_id,
                       Conversation.busy_until == lease).values(busy_until=datetime(2000, 1, 1)))
            db.commit()
