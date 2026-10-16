"""StoryGraph HTTP API."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.config import GRAPH_NAME
from app.db import ping
from app.graph.explorer import find_connection, resolve_entity, visible_graph
from app.llm.agent import answer_question

router = APIRouter(prefix="/api")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    chapter: int = Field(ge=1, le=1000)


@router.get("/health")
def health():
    return {"status": "ok" if ping() else "database_unavailable", "database": "falkordb", "graph": GRAPH_NAME}


@router.get("/graph")
def graph(chapter: int = 1):
    if chapter < 1 or chapter > 1000:
        raise HTTPException(status_code=422, detail="chapter must be between 1 and 1000")
    try:
        return visible_graph(chapter)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc


@router.get("/entities/resolve")
def resolve(name: str, chapter: int = 1):
    if chapter < 1 or chapter > 1000:
        raise HTTPException(status_code=422, detail="chapter must be between 1 and 1000")
    try:
        return {"matches": resolve_entity(name, chapter)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc


@router.get("/connection")
def connection(source: str, target: str, chapter: int = 1):
    if chapter < 1 or chapter > 1000:
        raise HTTPException(status_code=422, detail="chapter must be between 1 and 1000")
    try:
        return {"path": find_connection(source, target, chapter)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc


@router.post("/ask")
def ask(request: AskRequest):
    try:
        return answer_question(request.question, request.chapter)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Question service failed: {exc}") from exc
