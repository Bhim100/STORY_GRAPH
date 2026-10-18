"""StoryGraph HTTP API endpoints."""
import json
import re
from contextlib import contextmanager
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import GRAPH_NAME
from app.db import current_graph_name, ping
from app.graph.explorer import (
    find_connection,
    get_node_details,
    get_story_info,
    resolve_entity,
    visible_graph,
)
from app.importer import (
    SafeFetchError,
    UnsupportedFormatError,
    import_book_content,
    extract_and_seed_book_graph,
)
from app.llm.agent import answer_question
from app.storage import get_all_books, get_book, get_book_sources_dir, delete_book

router = APIRouter(prefix="/api")


@contextmanager
def scoped_graph(book_id: Optional[str]):
    """Context manager setting current_graph_name for the requested book."""
    if not book_id or book_id == "glass_orchard":
        token = current_graph_name.set(GRAPH_NAME)
        try:
            yield GRAPH_NAME
        finally:
            current_graph_name.reset(token)
    else:
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
        target = book.graph_name or f"story_{book_id}"
        token = current_graph_name.set(target)
        try:
            yield target
        finally:
            current_graph_name.reset(token)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000, description="Natural language question to investigate")
    chapter: int = Field(ge=1, le=100, description="Reader's current maximum reveal chapter")
    book_id: Optional[str] = Field(default="glass_orchard", description="Book/story identifier to investigate")


@router.get("/health")
def health():
    """Returns database health status and active default graph name."""
    is_live = ping()
    return {
        "status": "ok" if is_live else "database_unavailable",
        "database": "falkordb",
        "graph": GRAPH_NAME,
    }


# ==============================================================================
# Library / Book Management Endpoints
# ==============================================================================


@router.get("/books")
def list_books():
    """Lists all available books in the StoryGraph library with their metadata and import status."""
    try:
        books = get_all_books()
        return {"books": [b.model_dump() for b in books]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve book library: {exc}")


@router.get("/books/{book_id}")
def get_book_by_id(book_id: str):
    """Retrieves metadata, chapter boundaries, and import status for a specific book."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
    return book.model_dump()


@router.delete("/books/{book_id}")
def remove_book(book_id: str):
    """Deletes a book from the library catalog, source directory, and drops its FalkorDB graph."""
    if book_id == "glass_orchard":
        raise HTTPException(status_code=400, detail="Cannot delete the default baseline story 'The Glass Orchard'.")
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
    try:
        success = delete_book(book_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found.")
        return {"status": "success", "message": f"Story '{book.title}' was successfully removed."}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to remove story: {exc}")


@router.post("/books/{book_id}/extract-graph")
def trigger_extract_graph(book_id: str):
    """Triggers knowledge graph extraction and FalkorDB seeding for an existing book."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
    try:
        updated = extract_and_seed_book_graph(book_id)
        return updated.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph extraction failed: {exc}")


@router.post("/books")
async def add_book(request: Request):
    """Adds a new book to the user's StoryGraph library via file upload or source URL.
    
    Accepts multipart/form-data or application/json.
    """
    content_type = request.headers.get("content-type", "")
    title = ""
    author = ""
    description = ""
    source_type = "upload"
    file_format = "txt"
    raw_content = None
    source_url = None

    extract_graph = False
    if "multipart/form-data" in content_type:
        form = await request.form()
        title = str(form.get("title", "")).strip()
        author = str(form.get("author", "")).strip()
        description = str(form.get("description", "")).strip()
        source_type = str(form.get("source_type", "upload")).strip()
        file_format = str(form.get("format", "txt")).strip()
        source_url = str(form.get("source_url", "")).strip() or None
        extract_graph = str(form.get("extract_graph", "false")).strip().lower() in ("true", "1", "yes")

        upload_file = form.get("file")
        if upload_file and hasattr(upload_file, "read"):
            content_bytes = await upload_file.read()
            # Enforce max upload size 5MB
            if len(content_bytes) > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Uploaded file exceeds maximum allowable size of 5MB.")
            try:
                raw_content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    raw_content = content_bytes.decode("latin-1")
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"Could not decode uploaded file as text: {exc}")
    else:
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON request body: {exc}")
        title = str(body.get("title", "")).strip()
        author = str(body.get("author", "")).strip()
        description = str(body.get("description", "")).strip()
        source_type = str(body.get("source_type", "upload")).strip()
        file_format = str(body.get("format", "txt")).strip()
        source_url = str(body.get("source_url", "")).strip() or None
        raw_content = body.get("content")
        extract_graph = bool(body.get("extract_graph", False))

    # Auto-extract title, author, and description from front matter or JSON if not explicitly provided
    if not title or not author:
        meta_content = raw_content
        if not meta_content and source_type == "url" and source_url:
            try:
                from app.importer import fetch_source_url
                meta_content = fetch_source_url(source_url)
                raw_content = meta_content
            except Exception:
                pass

        if meta_content and file_format == "txt":
            from app.importer import parse_first_page_metadata
            front_meta = parse_first_page_metadata(meta_content, fallback_title=title)
            if not title and front_meta.get("title"):
                title = front_meta["title"]
            if not author and front_meta.get("author"):
                author = front_meta["author"]
            if not description and front_meta.get("description"):
                description = front_meta["description"]
        elif meta_content and file_format == "json":
            try:
                parsed_j = json.loads(meta_content)
                if not title and parsed_j.get("title"):
                    title = parsed_j["title"]
                if not author and parsed_j.get("author"):
                    author = parsed_j["author"]
                if not description and parsed_j.get("description"):
                    description = parsed_j.get("description", "")
            except Exception:
                pass

    if not title:
        raise HTTPException(status_code=400, detail="Book title is required.")
    if not author:
        raise HTTPException(status_code=400, detail="Book author is required.")

    try:
        book_meta = import_book_content(
            title=title,
            author=author,
            description=description,
            source_type=source_type,
            file_format=file_format,
            raw_content=raw_content,
            source_url=source_url,
            extract_graph=extract_graph,
        )
        return book_meta.model_dump()
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SafeFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to import book: {exc}")


@router.get("/books/{book_id}/chapters/{chapter_number}")
def get_book_chapter_content(book_id: str, chapter_number: int):
    """Retrieves full text and candidate entities for a specific chapter of a book."""
    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")

    if chapter_number < 1 or chapter_number > book.max_chapters:
        raise HTTPException(
            status_code=400,
            detail=f"Chapter {chapter_number} is out of bounds for '{book.title}' (1 - {book.max_chapters})."
        )

    # For Glass Orchard: generate chapter synopsis from revealed knowledge graph
    if book_id == "glass_orchard":
        with scoped_graph(book_id):
            graph_data = visible_graph(chapter_number)
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        sample_chars = [n["data"].get("label", "") for n in nodes if n["data"].get("kind") == "Character"][:6]
        return {
            "book_id": book_id,
            "chapter_number": chapter_number,
            "title": f"Chapter {chapter_number}",
            "word_count": max(120, len(nodes) * 35),
            "char_count": max(600, len(nodes) * 210),
            "preview": f"Glass Orchard Estate Investigation — Chapter {chapter_number} reading boundary.",
            "content": (
                f"=== THE GLASS ORCHARD — CHAPTER {chapter_number} ===\n\n"
                f"Active Narrative Investigation Boundary: Chapter {chapter_number} of {book.max_chapters}.\n\n"
                f"Archived estate evidence and testimony revealed up to this chapter establish "
                f"{len(nodes)} active narrative entities and {len(edges)} verified relationships.\n\n"
                f"Key active characters in this chapter: {', '.join(sample_chars) if sample_chars else 'None yet'}.\n\n"
                f"Use the Investigation Deck to query visible claims, or inspect individual node dossiers for exact textual excerpts."
            ),
            "candidate_entities": sample_chars,
        }

    # For imported text books: read from sources_dir/chapters.json
    sources_dir = get_book_sources_dir(book_id)
    chapters_file = sources_dir / "chapters.json"
    if not chapters_file.exists():
        raise HTTPException(status_code=404, detail=f"No chapter data found for book '{book_id}'.")

    try:
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f).get("chapters", [])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read chapters for '{book_id}': {exc}")

    ch_data = next((c for c in chapters if c["chapter_number"] == chapter_number), None)
    if not ch_data:
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_number} not found in book '{book_id}'.")

    return {
        "book_id": book_id,
        "chapter_number": ch_data["chapter_number"],
        "title": ch_data.get("title", f"Chapter {chapter_number}"),
        "word_count": ch_data.get("word_count", 0),
        "char_count": ch_data.get("char_count", 0),
        "preview": ch_data.get("preview", ""),
        "content": ch_data.get("content", ""),
        "candidate_entities": ch_data.get("candidate_entities", []),
    }


@router.post("/books/{book_id}/extract-graph")
def extract_graph_for_book(book_id: str):
    """Extracts candidate entities and seeds FalkorDB graph for an imported book."""
    try:
        book_meta = extract_and_seed_book_graph(book_id)
        return book_meta.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph extraction failed: {exc}")


@router.delete("/books/{book_id}")
def remove_book(book_id: str):
    """Deletes a story from the library catalog, removes its files, and drops its graph."""
    if book_id == "glass_orchard":
        raise HTTPException(status_code=400, detail="The default 'The Glass Orchard' mystery cannot be removed.")

    book = get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")

    try:
        success = delete_book(book_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Failed to delete book '{book_id}'.")
        return {"status": "deleted", "book_id": book_id, "message": f"Story '{book.title}' was successfully removed."}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to remove book: {exc}")


# ==============================================================================
# Graph Exploration & Question Endpoints (Book Scoped)
# ==============================================================================


@router.get("/story")
def story(book_id: Optional[str] = Query(default=None, description="Book/story identifier")):
    """Returns story metadata and maximum narrative chapter count for the selected book."""
    if book_id and book_id != "glass_orchard":
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
        return {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "description": book.description,
            "max_chapters": book.max_chapters,
            "status": book.status,
            "status_message": book.status_message,
        }
    try:
        return get_story_info()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Story information is currently unavailable. Please check that the graph database is running."
        ) from exc


@router.get("/graph")
def graph(
    chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary"),
    book_id: Optional[str] = Query(default=None, description="Book/story identifier"),
):
    """Returns all nodes and edges visible up to the requested chapter boundary for the selected book."""
    if book_id and book_id != "glass_orchard":
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
        if not book.graph_name or book.status != "ready":
            return {
                "nodes": [],
                "edges": [],
                "book_id": book.id,
                "status": book.status,
                "message": book.status_message or "Graph extraction pending for this book.",
                "max_chapters": book.max_chapters,
            }
    with scoped_graph(book_id):
        try:
            return visible_graph(chapter)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Graph service is currently unavailable. Please check that the graph database is running."
            ) from exc


@router.get("/entities/resolve")
def resolve(
    name: str = Query(min_length=1, max_length=200, description="Entity name or alias"),
    chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary"),
    book_id: Optional[str] = Query(default=None, description="Book/story identifier"),
):
    """Resolves an entity name against visible entities at chapter boundary for the selected book."""
    if book_id and book_id != "glass_orchard":
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
        if not book.graph_name or book.status != "ready":
            return {"matches": []}
    with scoped_graph(book_id):
        try:
            matches = resolve_entity(name, chapter)
            return {"matches": matches}
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Entity resolution service is currently unavailable. Please check that the graph database is running."
            ) from exc


@router.get("/nodes/{node_id}")
def node_details(
    node_id: str,
    chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary"),
    book_id: Optional[str] = Query(default=None, description="Book/story identifier"),
):
    """Returns case notes, visible relationships, and supporting evidence for a selected node."""
    if book_id and book_id != "glass_orchard":
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
        if not book.graph_name or book.status != "ready":
            raise HTTPException(
                status_code=404,
                detail=f"Graph data is pending extraction for book '{book.title}'."
            )
    with scoped_graph(book_id):
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
            raise HTTPException(
                status_code=503,
                detail="Node details service is currently unavailable. Please check that the graph database is running."
            ) from exc


@router.get("/connection")
def connection(
    source: str = Query(min_length=1, max_length=100, description="Source entity ID"),
    target: str = Query(min_length=1, max_length=100, description="Target entity ID"),
    chapter: int = Query(default=1, ge=1, le=100, description="Chapter boundary"),
    book_id: Optional[str] = Query(default=None, description="Book/story identifier"),
):
    """Finds shortest spoiler-safe, evidence-supported path between two entities for the selected book."""
    if book_id and book_id != "glass_orchard":
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
        if not book.graph_name or book.status != "ready":
            return {"path": None}
    with scoped_graph(book_id):
        try:
            path = find_connection(source, target, chapter)
            return {"path": path}
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Connection pathfinding service is currently unavailable. Please check that the graph database is running."
            ) from exc


@router.post("/ask")
def ask(request: AskRequest):
    """Natural-language question answering scoped strictly to the selected book."""
    book_id = request.book_id or "glass_orchard"
    if book_id != "glass_orchard":
        book = get_book(book_id)
        if not book:
            raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found in library.")
        if not book.graph_name or book.status != "ready":
            return {
                "status": "import_pending",
                "answer": (
                    f"Investigation for '{book.title}': The text has been parsed into {book.max_chapters} chapters "
                    f"with reading boundaries preserved (current position: Chapter {request.chapter}). "
                    f"Automated relation extraction is not yet configured for this book; no graph claims or evidence items are available."
                ),
                "resolved_entities": [],
                "nodes": [],
                "relationships": [],
                "evidence": [],
                "path": None,
            }

    with scoped_graph(book_id):
        try:
            return answer_question(request.question, request.chapter)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Question answering service is temporarily unavailable. Please try again shortly."
            ) from exc
