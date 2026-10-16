"""Seed JSON mystery stories into FalkorDB graph."""
import json
from pathlib import Path
from typing import Optional, Dict, Any
from app.db import get_graph


def load_story_json(file_path: Path) -> Dict[str, Any]:
    """Loads a story graph definition from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_story_to_falkordb(data: Dict[str, Any], graph_name: Optional[str] = None) -> None:
    """Seeds story nodes and relationships into FalkorDB."""
    graph = get_graph(graph_name)
    # Clear existing graph data before seeding
    try:
        graph.delete()
    except Exception:
        pass

    # Node and edge ingestion will be expanded in Part 2
    # Placeholder query to establish graph presence
    graph.query("CREATE (:Story {id: $id, title: $title})", {
        "id": data.get("id", "glass_orchard"),
        "title": data.get("title", "The Glass Orchard")
    })
