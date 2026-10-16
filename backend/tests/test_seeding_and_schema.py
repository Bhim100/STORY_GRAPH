"""Tests for story loading, referential integrity, and graph seeding."""
from pathlib import Path
import pytest
from app.graph.seed import load_story_dataset, validate_story_integrity, seed_story_to_falkordb
from app.db import get_graph

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stories" / "glass_orchard.json"


def test_story_dataset_loading():
    """Verify that glass_orchard.json adheres strictly to Pydantic models."""
    assert DATA_PATH.exists(), "glass_orchard.json does not exist"
    story = load_story_dataset(DATA_PATH)
    assert story.story_id == "glass_orchard"
    assert len(story.characters) == 8
    assert len(story.events) == 8
    assert len(story.locations) == 3
    assert len(story.factions) == 2
    assert len(story.claims) >= 15
    assert len(story.evidence) >= 10


def test_story_integrity():
    """Verify referential integrity of claims, evidence, and entity references."""
    story = load_story_dataset(DATA_PATH)
    # Should not raise any ValueError
    validate_story_integrity(story)


def test_seed_to_falkordb():
    """Verify that seeding populates FalkorDB accurately."""
    story = load_story_dataset(DATA_PATH)
    seed_story_to_falkordb(story, graph_name="test_glass_orchard")

    graph = get_graph("test_glass_orchard")

    # Verify character count
    res = graph.query("MATCH (c:Character) RETURN count(c)")
    assert res.result_set[0][0] == 8

    # Verify event count
    res = graph.query("MATCH (e:Event) RETURN count(e)")
    assert res.result_set[0][0] == 8

    # Verify claim count
    res = graph.query("MATCH (cl:Claim) RETURN count(cl)")
    assert res.result_set[0][0] == len(story.claims)

    # Verify evidence count
    res = graph.query("MATCH (evi:Evidence) RETURN count(evi)")
    assert res.result_set[0][0] == len(story.evidence)

    # Clean up test graph
    try:
        graph.delete()
    except Exception:
        pass
