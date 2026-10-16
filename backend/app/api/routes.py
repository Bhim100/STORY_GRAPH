"""StoryGraph HTTP API endpoints."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from app.config import GRAPH_NAME
from app.db import ping
from app.graph.explorer import (
    find_connection,
    get_node_details,
    get_story_info,
    resolve_entity,
    visible_graph,
)
from app.llm.agent import answer_question

router = APIRouter(prefix="/api")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, description="Natural language question to investigate")
    chapter: int = Field(ge=1, le=100, description="Reader's current maximum reveal chapter")


@router.get("/health")
def health():
    """Returns database health status and active graph name."""
    is_live = ping()
    return {
        "status": "ok" if is_live else "database_unavailable",
        "database": "falkordb",
        "graph": GRAPH_NAME,
    }


@router.get("/story")
def story():
    """Returns story metadata and maximum narrative chapter count."""
    try:
        return get_story_info()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Story information unavailable: {exc}") from exc


@router.get("/graph")
def graph(chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary")):
    """Returns all nodes and edges visible up to the requested chapter boundary."""
    try:
        return visible_graph(chapter)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph unavailable: {exc}") from exc


@router.get("/entities/resolve")
def resolve(
    name: str = Query(min_length=1, max_length=200, description="Entity name or alias"),
    chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary"),
):
    """Resolves an entity name against visible entities at chapter boundary."""
    try:
        matches = resolve_entity(name, chapter)
        return {"matches": matches}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Resolution service unavailable: {exc}") from exc


@router.get("/nodes/{node_id}")
def node_details(
    node_id: str,
    chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary"),
):
    """Returns case notes, visible relationships, and supporting evidence for a selected node."""
    try:
        details = get_node_details(node_id, chapter)
        if not details:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{node_id}' is not revealed or does not exist at Chapter {chapter}."
            )
        return details
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Node details service failed: {exc}") from exc


@router.get("/connection")
def connection(
    source: str = Query(min_length=1, max_length=100, description="Source entity ID"),
    target: str = Query(min_length=1, max_length=100, description="Target entity ID"),
    chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary"),
):
    """Finds shortest spoiler-safe, evidence-supported path between two entities."""
    try:
        path = find_connection(source, target, chapter)
        return {"path": path}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Connection service failed: {exc}") from exc


@router.post("/ask")
def ask(request: AskRequest):
    """Natural-language question answering through the Phase 3 AI Agent."""
    try:
        return answer_question(request.question, request.chapter)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Question answering service failed: {exc}") from exc
