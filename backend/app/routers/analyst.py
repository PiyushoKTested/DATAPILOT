"""Natural-language data analyst endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_owned_dataset, load_frame, resolve_version
from ..models import ChatMessage, Conversation, User
from ..schemas import (
    ConversationOut,
    LlmStatus,
    QueryRequest,
    QueryResponse,
)
from ..services.nlp import analyst, ollama_client
from ..services.nlp.rule_engine import build_suggestions

router = APIRouter(tags=["analyst"])


@router.get("/llm/status", response_model=LlmStatus)
def llm_status() -> LlmStatus:
    return LlmStatus(**ollama_client.status())


@router.get("/datasets/{dataset_id}/query/suggestions")
def query_suggestions(
    dataset_id: int,
    version_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, version_id)
    frame = load_frame(version)
    return {
        "suggestions": build_suggestions(frame),
        "llm": ollama_client.status(),
    }


@router.post("/datasets/{dataset_id}/query", response_model=QueryResponse)
def ask_question(
    dataset_id: int,
    payload: QueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryResponse:
    dataset = get_owned_dataset(db, user, dataset_id)
    version = resolve_version(db, dataset, payload.version_id)
    frame = load_frame(version)

    # Resolve or create the conversation.
    conversation = None
    if payload.conversation_id is not None:
        conversation = db.get(Conversation, payload.conversation_id)
        if conversation is None or conversation.dataset_id != dataset.id:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    if conversation is None:
        title = payload.question.strip()[:80]
        conversation = Conversation(dataset_id=dataset.id, title=title)
        db.add(conversation)
        db.flush()

    user_message = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=payload.question,
        engine="system",
    )
    db.add(user_message)

    outcome = analyst.answer(
        payload.question, frame, prefer_llm=payload.prefer_llm
    )

    engine = outcome.get("engine", "rule_based")
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=outcome.get("explanation", ""),
        engine=engine,
        intent=outcome.get("intent"),
        payload={
            "operation": outcome.get("operation"),
            "result": outcome.get("result"),
            "chart": outcome.get("chart"),
            "verified": outcome.get("verified", False),
            "warnings": outcome.get("warnings", []),
            "supported_examples": outcome.get("supported_examples", []),
            "ok": outcome.get("ok", True),
        },
        model_name=outcome.get("model_name"),
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    labels = {
        "llm": "Local LLM (Ollama)",
        "rule_based": "Rule-based engine",
        "system": "System",
    }
    return QueryResponse(
        answer=outcome.get("explanation", ""),
        engine=engine if engine in labels else "rule_based",
        engine_label=labels.get(engine, "Rule-based engine"),
        intent=outcome.get("intent", "unsupported"),
        operation=outcome.get("operation", {}),
        result={
            **(outcome.get("result") or {}),
        },
        explanation=outcome.get("explanation", ""),
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        supported_examples=outcome.get("supported_examples", []),
        warnings=outcome.get("warnings", []),
        chart=outcome.get("chart"),
    )


@router.get("/datasets/{dataset_id}/conversations", response_model=list[ConversationOut])
def list_conversations(
    dataset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationOut]:
    get_owned_dataset(db, user, dataset_id)
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.dataset_id == dataset_id)
        .order_by(Conversation.created_at.desc())
    ).unique().all()
    return [ConversationOut.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationOut:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    get_owned_dataset(db, user, conversation.dataset_id)
    return ConversationOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204, response_model=None)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    get_owned_dataset(db, user, conversation.dataset_id)
    db.delete(conversation)
    db.commit()

