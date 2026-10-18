"""Tests for natural-language investigation query routing and graph extraction."""
import pytest
from app.db import ping, current_graph_name
from app.llm.agent import answer_question
from app.llm.router import route_question, QuestionType

requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


def test_investigating_case_routing_classification():
    """Verify 'Who is investigating the case?' routes to collection_query, not unresolved entity."""
    res = route_question("Who is investigating the case?", chapter=1)
    assert res["question_type"] == QuestionType.COLLECTION_QUERY
    assert res["status"] == "ok"
    assert "investigating the case" not in res.get("unresolved_entities", [])
    assert len(res.get("unresolved_entities", [])) == 0


def test_investigation_phrasing_variations():
    """Verify various natural language phrasings of investigator queries route to collection_query."""
    variations = [
        "Who is investigating the case?",
        "Who is the investigator?",
        "Who is investigating?",
        "Who investigates the disappearance?",
        "Who is looking after the case?",
        "Who is in charge of the investigation?",
    ]
    for q in variations:
        res = route_question(q, chapter=1)
        assert res["question_type"] == QuestionType.COLLECTION_QUERY
        assert res["status"] == "ok"
        assert len(res.get("unresolved_entities", [])) == 0


@requires_falkordb
def test_silver_blaze_investigators_at_chapter_1():
    """Verify Silver Blaze returns Inspector Gregory and Sherlock Holmes with distinguished roles."""
    token = current_graph_name.set("story_i_silver_blaze")
    try:
        res = answer_question("Who is investigating the case?", chapter=1)
        assert res["status"] == "collection_query"
        assert res["status"] != "unresolved_entity"

        node_names = [n["name"] for n in res.get("nodes", [])]
        assert "Inspector Gregory" in node_names
        assert "Sherlock Holmes" in node_names

        # Verify distinguished roles
        gregory_node = next(n for n in res["nodes"] if n["name"] == "Inspector Gregory")
        assert "Police Detective Inspector" in gregory_node["role"] or "Inspector" in gregory_node["role"]

        holmes_node = next(n for n in res["nodes"] if n["name"] == "Sherlock Holmes")
        assert "Consulting Detective" in holmes_node["role"] or "Detective" in holmes_node["role"]

        # Verify evidence is returned
        assert len(res.get("evidence", [])) > 0
        ans = res["answer"]
        assert "Inspector Gregory" in ans
        assert "Sherlock Holmes" in ans
        assert "Unresolved Entity" not in ans
    finally:
        current_graph_name.reset(token)


@requires_falkordb
def test_investigation_query_spoiler_boundary():
    """Verify Chapter 1 query does not include Chapter 2 evidence."""
    token = current_graph_name.set("story_i_silver_blaze")
    try:
        res_ch1 = answer_question("Who is investigating the case?", chapter=1)
        for ev in res_ch1.get("evidence", []):
            assert ev["reveal_chapter"] <= 1
            assert ev["source_chapter"] <= 1

        # In Chapter 1, Chapter 2 specific evidence is absent
        ans_ch1 = res_ch1["answer"]
        assert "extremely competent officer" not in ans_ch1
    finally:
        current_graph_name.reset(token)


@requires_falkordb
def test_glass_orchard_no_investigator():
    """Verify Glass Orchard correctly indicates no active investigators at Chapter 1 without error."""
    token = current_graph_name.set("glass_orchard")
    try:
        res = answer_question("Who is investigating the case?", chapter=1)
        assert res["status"] == "collection_query"
        assert res["status"] != "unresolved_entity"
        assert len(res.get("nodes", [])) == 0
        assert "no characters with active investigation relationships" in res["answer"].lower()
    finally:
        current_graph_name.reset(token)
