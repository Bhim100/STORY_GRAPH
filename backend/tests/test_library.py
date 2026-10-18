"""Tests for StoryGraph library management, book imports, format validation, and graph isolation."""
import json
import pytest
from fastapi.testclient import TestClient

from app.db import ping
from app.main import app

from pathlib import Path
import tempfile

client = TestClient(app)
requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


@pytest.fixture(autouse=True)
def isolate_library_catalog(monkeypatch):
    """Isolate library catalog and sources to a temporary directory so tests do not pollute real catalog."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_lib_dir = Path(temp_dir) / "library"
        test_sources_dir = test_lib_dir / "sources"
        test_catalog_path = test_lib_dir / "catalog.json"
        test_lib_dir.mkdir(parents=True, exist_ok=True)
        test_sources_dir.mkdir(parents=True, exist_ok=True)

        from app.storage import GLASS_ORCHARD_DEFAULT
        with open(test_catalog_path, "w", encoding="utf-8") as f:
            json.dump({"books": [GLASS_ORCHARD_DEFAULT.model_dump()]}, f, indent=2)

        monkeypatch.setattr("app.storage.LIBRARY_DIR", test_lib_dir)
        monkeypatch.setattr("app.storage.CATALOG_PATH", test_catalog_path)
        monkeypatch.setattr("app.storage.SOURCES_DIR", test_sources_dir)
        yield


def test_list_books():
    """Verify GET /api/books returns available books including default Glass Orchard."""
    res = client.get("/api/books")
    assert res.status_code == 200
    data = res.json()
    assert "books" in data
    assert len(data["books"]) >= 1
    glass_orchard = next((b for b in data["books"] if b["id"] == "glass_orchard"), None)
    assert glass_orchard is not None
    assert glass_orchard["title"] == "The Glass Orchard"
    assert glass_orchard["status"] == "ready"
    assert glass_orchard["max_chapters"] == 8


def test_get_book_glass_orchard():
    """Verify GET /api/books/glass_orchard returns book metadata and chapters."""
    res = client.get("/api/books/glass_orchard")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "glass_orchard"
    assert data["status"] == "ready"
    assert data["max_chapters"] == 8
    assert len(data["chapters"]) == 8


def test_get_nonexistent_book():
    """Verify GET /api/books/nonexistent returns 404."""
    res = client.get("/api/books/nonexistent_book_id_999")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_add_book_plain_text():
    """Verify adding a plain text book parses chapters and marks status as import_pending."""
    txt_content = """Chapter 1: The Arrival
Holmes and Watson arrived at the desolate moor as dusk was settling.

Chapter 2: The Footprints
The following morning, strange animal footprints were observed near the gates.

Chapter 3: The Revelation
A mysterious figure was observed watching from the granite tor.
"""
    res = client.post("/api/books", json={
        "title": "The Moorland Mystery",
        "author": "Arthur Conan Doyle",
        "description": "A classic Gothic detective investigation across the moors.",
        "source_type": "upload",
        "format": "txt",
        "content": txt_content,
    })
    assert res.status_code == 200
    book = res.json()
    assert "moorland_mystery" in book["id"]
    assert book["title"] == "The Moorland Mystery"
    assert book["format"] == "txt"
    assert book["status"] == "import_pending"
    assert book["max_chapters"] == 3
    assert len(book["chapters"]) == 3
    assert "The Arrival" in book["chapters"][0]["title"]
    assert "The Footprints" in book["chapters"][1]["title"]
    assert "The Revelation" in book["chapters"][2]["title"]


def test_add_book_unsupported_format_pdf():
    """Verify trying to add a PDF book returns a clear unsupported-format error explaining parser absence."""
    res = client.post("/api/books", json={
        "title": "A PDF Investigation",
        "author": "Anonymous",
        "source_type": "upload",
        "format": "pdf",
        "content": "%PDF-1.4 dummy binary content",
    })
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "PDF" in detail
    assert "not installed" in detail or "unsupported" in detail.lower()


def test_add_book_unsupported_format_epub():
    """Verify trying to add an EPUB book returns a clear unsupported-format error explaining parser absence."""
    res = client.post("/api/books", json={
        "title": "An EPUB Mystery",
        "author": "Anonymous",
        "source_type": "upload",
        "format": "epub",
        "content": "PK dummy epub content",
    })
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "EPUB" in detail
    assert "not installed" in detail or "unsupported" in detail.lower()


def test_add_book_ssrf_url_protection():
    """Verify that source URLs pointing to internal or private IP addresses are strictly rejected."""
    # Attempting localhost / 127.0.0.1
    res = client.post("/api/books", json={
        "title": "Malicious Internal URL",
        "author": "Attacker",
        "source_type": "url",
        "format": "txt",
        "source_url": "http://127.0.0.1:8000/api/health",
    })
    assert res.status_code == 400
    detail = res.json()["detail"].lower()
    assert "prohibited" in detail or "security" in detail or "localhost" in detail or "internal" in detail


def test_add_book_missing_fields_validation():
    """Verify input validation requires title and author."""
    res1 = client.post("/api/books", json={"title": "", "author": "Someone"})
    assert res1.status_code == 400

    res2 = client.post("/api/books", json={"title": "Some Title", "author": ""})
    assert res2.status_code == 400


@requires_falkordb
def test_cross_book_graph_isolation():
    """Verify that queries for a second book never return or leak Glass Orchard graph data or evidence."""
    # 1. First, create a second book
    res_create = client.post("/api/books", json={
        "title": "The Cipher of Saint Jude",
        "author": "Father Brown",
        "description": "A clerical puzzle involving a locked vestry.",
        "source_type": "upload",
        "format": "txt",
        "content": "Chapter 1: The Missing Chalice\nFather Brown inspected the empty altar.",
    })
    assert res_create.status_code == 200
    second_book = res_create.json()
    second_id = second_book["id"]

    # 2. Fetch graph for the second book: must NOT contain Glass Orchard characters (Halden, Elias, etc.)
    res_graph_2 = client.get(f"/api/graph?chapter=1&book_id={second_id}")
    assert res_graph_2.status_code == 200
    graph_data_2 = res_graph_2.json()
    assert graph_data_2["status"] == "import_pending"
    assert len(graph_data_2["nodes"]) == 0
    node_labels_2 = [n["data"]["label"] for n in graph_data_2.get("nodes", [])]
    assert "Dr. Pavel Halden" not in node_labels_2
    assert "Elias Thorne" not in node_labels_2

    # 3. Fetch story info for second book
    res_story_2 = client.get(f"/api/story?book_id={second_id}")
    assert res_story_2.status_code == 200
    story_2 = res_story_2.json()
    assert story_2["title"] == "The Cipher of Saint Jude"
    assert story_2["status"] == "import_pending"

    # 4. Ask a question for the second book: must NOT answer with Glass Orchard culprits or claims
    res_ask_2 = client.post("/api/ask", json={
        "question": "Who is the killer?",
        "chapter": 1,
        "book_id": second_id,
    })
    assert res_ask_2.status_code == 200
    ask_data_2 = res_ask_2.json()
    assert ask_data_2["status"] == "import_pending"
    assert "Cipher of Saint Jude" in ask_data_2["answer"]
    assert "Dr. Pavel Halden" not in ask_data_2["answer"]
    assert "cider" not in ask_data_2["answer"].lower()

    # 5. Fetch graph for Glass Orchard: must remain completely unaffected and intact!
    res_glass = client.get("/api/graph?chapter=1&book_id=glass_orchard")
    assert res_glass.status_code == 200
    glass_data = res_glass.json()
    glass_node_ids = [n["data"]["id"] for n in glass_data["nodes"]]
    assert "c_elias_thorne" in glass_node_ids
    assert "c_mara_voss" in glass_node_ids


def test_get_chapter_content():
    """Verify GET /api/books/{book_id}/chapters/{chapter_number} returns full chapter text."""
    # Test for default Glass Orchard
    res_go = client.get("/api/books/glass_orchard/chapters/1")
    assert res_go.status_code == 200
    go_ch = res_go.json()
    assert go_ch["chapter_number"] == 1
    assert "THE GLASS ORCHARD" in go_ch["content"]
    assert len(go_ch["candidate_entities"]) > 0

    # Test for text story
    res_txt = client.get("/api/books/the_harrington_mystery/chapters/1")
    if res_txt.status_code == 200:
        ch = res_txt.json()
        assert ch["chapter_number"] == 1
        assert "Detective Vance" in ch["content"]
        assert ch["word_count"] > 0


@requires_falkordb
def test_add_book_with_candidate_graph_extraction():
    """Verify adding a text book with extract_graph=True extracts candidate characters and seeds FalkorDB."""
    sample_story = """Chapter 1: The Arrival
Inspector Lestrade visited Blackwood Manor to consult Lord Harrington.

Chapter 2: The Stolen Emerald
The safe in the study was emptied. Lady Eleanor suspected the mysterious stranger.
"""
    res = client.post("/api/books", json={
        "title": "The Blackwood Mystery",
        "author": "Arthur Sterling",
        "description": "An investigative emerald heist.",
        "source_type": "upload",
        "format": "txt",
        "content": sample_story,
        "extract_graph": True,
    })
    assert res.status_code == 200
    book = res.json()
    assert book["status"] == "ready"
    assert book["graph_name"] is not None
    assert book["max_chapters"] == 2

    # Verify graph can be queried for Chapter 1
    res_graph = client.get(f"/api/graph?chapter=1&book_id={book['id']}")
    assert res_graph.status_code == 200
    graph = res_graph.json()
    assert len(graph["nodes"]) > 0
    node_labels = [n["data"]["label"] for n in graph["nodes"]]
    assert any("Inspector Lestrade" in lbl or "Lord Harrington" in lbl for lbl in node_labels)


def test_parse_first_page_metadata_formats():
    """Verify parsing title, author, and description across standard opening page formats."""
    from app.importer import parse_first_page_metadata

    # 1. Standard Title followed by By Author
    txt1 = """The Sign of the Four
By Sir Arthur Conan Doyle

Chapter 1: The Science of Deduction
"""
    m1 = parse_first_page_metadata(txt1)
    assert m1["title"] == "The Sign of the Four"
    assert m1["author"] == "Sir Arthur Conan Doyle"

    # 2. Gutenberg Header
    txt2 = """The Project Gutenberg eBook of A Study in Scarlet, by Arthur Conan Doyle

Chapter 1: Mr. Sherlock Holmes
"""
    m2 = parse_first_page_metadata(txt2)
    assert m2["title"] == "A Study in Scarlet"
    assert m2["author"] == "Arthur Conan Doyle"

    # 3. Tagged Header
    txt3 = """Title: The Murder on the Links
Author: Agatha Christie
Description: An intricate French golf course investigation

Chapter 1: A Fellow Traveller
"""
    m3 = parse_first_page_metadata(txt3)
    assert m3["title"] == "The Murder on the Links"
    assert m3["author"] == "Agatha Christie"
    assert m3["description"] == "An intricate French golf course investigation"

    # 4. ALL CAPS Title & Multiline BY
    txt4 = """THE ADVENTURES OF SHERLOCK HOLMES

BY

ARTHUR CONAN DOYLE

Chapter 1: A Scandal in Bohemia
"""
    m4 = parse_first_page_metadata(txt4)
    assert m4["title"].lower() == "the adventures of sherlock holmes"
    assert m4["author"] == "Arthur Conan Doyle"


def test_add_book_auto_fill_from_first_page():
    """Verify adding a story without explicit title/author automatically infers them from first page."""
    sample_text = """The Hound of the Baskervilles
by Arthur Conan Doyle

Chapter 1: Mr. Sherlock Holmes
Holmes and Watson discussed the mysterious walking stick left by Dr. Mortimer.

Chapter 2: The Curse of the Baskervilles
Sir Charles Baskerville was found dead near the yew alley.
"""
    # Leave title and author empty
    res = client.post("/api/books", json={
        "title": "",
        "author": "",
        "source_type": "upload",
        "format": "txt",
        "content": sample_text,
    })
    assert res.status_code == 200
    book = res.json()
    assert book["title"] == "The Hound of the Baskervilles"
    assert book["author"] == "Arthur Conan Doyle"
    assert book["max_chapters"] == 2

