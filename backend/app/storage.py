"""Storage and catalog manager for StoryGraph books and libraries."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from app.models import BookMetadata, ChapterMetadata

# Base paths
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
LIBRARY_DIR = DATA_DIR / "library"
CATALOG_PATH = LIBRARY_DIR / "catalog.json"
SOURCES_DIR = LIBRARY_DIR / "sources"

GLASS_ORCHARD_DEFAULT = BookMetadata(
    id="glass_orchard",
    title="The Glass Orchard",
    author="Elias Thorne Estate Archive",
    description="An aristocratic greenhouse estate murder mystery running across 8 chapters.",
    format="json",
    source_type="bundled",
    status="ready",
    status_message="Complete knowledge graph loaded with 8 chapters of spoiler boundaries.",
    max_chapters=8,
    graph_name="glass_orchard",
    created_at="2026-10-18T00:00:00Z",
    chapters=[
        ChapterMetadata(chapter_number=i, title=f"Chapter {i}", preview="Glass Orchard estate investigation.")
        for i in range(1, 9)
    ]
)


def _ensure_dirs() -> None:
    """Ensures library and sources directories exist."""
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)


def init_catalog() -> None:
    """Initializes the catalog file with the default Glass Orchard story if needed."""
    _ensure_dirs()
    if not CATALOG_PATH.exists():
        initial_data = {
            "books": [GLASS_ORCHARD_DEFAULT.model_dump()]
        }
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, indent=2)


def get_all_books() -> List[BookMetadata]:
    """Retrieves all books registered in the StoryGraph library catalog."""
    init_catalog()
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        books_data = data.get("books", [])
        return [BookMetadata.model_validate(b) for b in books_data]
    except Exception as exc:
        # Fallback to default in case of read error
        return [GLASS_ORCHARD_DEFAULT]


def get_book(book_id: str) -> Optional[BookMetadata]:
    """Retrieves metadata for a specific book by ID."""
    books = get_all_books()
    for b in books:
        if b.id == book_id:
            return b
    return None


def save_book(book: BookMetadata) -> None:
    """Adds or updates a book in the library catalog."""
    init_catalog()
    books = get_all_books()
    updated = False
    for i, existing in enumerate(books):
        if existing.id == book.id:
            books[i] = book
            updated = True
            break
    if not updated:
        books.append(book)

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"books": [b.model_dump() for b in books]}, f, indent=2)


def generate_book_id(title: str) -> str:
    """Generates a stable, safe slug identifier for a book title."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", title.strip().lower()).strip("_")
    if not clean:
        clean = "story"
    base_id = clean[:32]
    candidate = base_id
    counter = 1
    existing_ids = {b.id for b in get_all_books()}
    while candidate in existing_ids:
        candidate = f"{base_id}_{counter}"
        counter += 1
    return candidate


def get_book_sources_dir(book_id: str) -> Path:
    """Returns directory path for storing raw source text and segmented chapters."""
    _ensure_dirs()
    book_dir = SOURCES_DIR / book_id
    book_dir.mkdir(parents=True, exist_ok=True)
    return book_dir


def delete_book(book_id: str) -> bool:
    """Removes a book from the library catalog, deletes its sources directory, and drops its FalkorDB graph."""
    if book_id == "glass_orchard":
        raise ValueError("Cannot remove the default bundled 'The Glass Orchard' mystery.")

    init_catalog()
    books = get_all_books()
    book_to_delete = next((b for b in books if b.id == book_id), None)
    if not book_to_delete:
        return False

    # 1. Remove from catalog.json
    remaining_books = [b for b in books if b.id != book_id]
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"books": [b.model_dump() for b in remaining_books]}, f, indent=2)

    # 2. Remove sources directory
    book_dir = SOURCES_DIR / book_id
    if book_dir.exists():
        import shutil
        try:
            shutil.rmtree(book_dir)
        except Exception:
            pass

    # 3. Clean FalkorDB graph
    graph_name = book_to_delete.graph_name or f"story_{book_id}"
    try:
        from app.db import get_falkordb_client
        client = get_falkordb_client()
        g = client.select_graph(graph_name)
        g.delete()
    except Exception:
        pass

    return True
