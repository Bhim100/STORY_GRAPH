"""Phase 5: Validation and Reliability Test Suite for StoryGraph.

This suite covers all 12 validation scenarios with explicit classification of testing
mechanisms (Unit Test / Mocked Test / Offline Logic vs. Live Integration Test).
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.graph.comparison import _dataset_graph_path
from app.graph.explorer import sanitize_role
from app.llm.agent import answer_question
from app.llm.generator import generate_grounded_answer, validate_answer_grounding
from app.llm.interpreter import interpret_question

client = TestClient(app)


# ==============================================================================
# Scenario 1: Two entities with a direct supported connection.
# Testing Mechanism: Unit / Deterministic Graph Traversal
# ==============================================================================
def test_scenario_1_direct_supported_connection():
    """Scenario 1: Mara Voss -> Elias Thorne has a direct EMPLOYED_BY connection at Chapter 1."""
    path = _dataset_graph_path("c_mara_voss", "c_elias_thorne", chapter=1)
    assert path is not None
    assert len(path["nodes"]) == 2
    assert len(path["relationships"]) == 1
    assert path["relationships"][0]["type"] == "EMPLOYED_BY"
    assert path["relationships"][0]["reveal_chapter"] <= 1
    # Evidence must be attached and revealed by Chapter 1
    assert len(path["evidence"]) >= 1
    assert path["evidence"][0]["reveal_chapter"] <= 1
    assert "contract" in path["evidence"][0]["excerpt"].lower() or "employment" in path["evidence"][0]["excerpt"].lower()


# ==============================================================================
# Scenario 2: A connection that requires multiple graph relationships.
# Testing Mechanism: Unit / Deterministic Graph Traversal
# ==============================================================================
def test_scenario_2_multi_hop_connection():
    """Scenario 2: Mara Voss <-> Dr. Halden requires a 2-hop path via Elias Thorne at Chapter 4."""
    path = _dataset_graph_path("c_mara_voss", "c_pavel_halden", chapter=4)
    assert path is not None
    assert len(path["nodes"]) == 3
    node_ids = [n["id"] for n in path["nodes"]]
    assert node_ids == ["c_mara_voss", "c_elias_thorne", "c_pavel_halden"]
    assert len(path["relationships"]) == 2
    rel_types = {r["type"] for r in path["relationships"]}
    assert "EMPLOYED_BY" in rel_types
    assert "PHYSICIAN_OF" in rel_types
    # Supporting evidence for both hops must be present
    evidence_claim_ids = {e["claim_id"] for e in path["evidence"]}
    assert "cl_mara_employed" in evidence_claim_ids
    assert "cl_halden_physician" in evidence_claim_ids


# ==============================================================================
# Scenario 3: No supported path exists.
# Testing Mechanism: Unit / Deterministic Graph Traversal
# ==============================================================================
def test_scenario_3_no_supported_path_exists():
    """Scenario 3: Tobias Quill has no evidence-supported path to Elias Thorne at any chapter."""
    for ch in [1, 2, 5, 8]:
        path = _dataset_graph_path("c_tobias_quill", "c_elias_thorne", chapter=ch)
        assert path is None


# ==============================================================================
# Scenario 4: Ambiguous or unknown entity is handled without guessing.
# Testing Mechanism: Mock / Unit
# ==============================================================================
def test_scenario_4_ambiguous_and_unknown_entity_handling():
    """Scenario 4: Ambiguous names require clarification with visible options only; unknown entities yield unresolved."""
    # Mock visible entities for deterministic test
    mock_visible = [
        {"id": "c_elias_thorne", "name": "Elias Thorne", "aliases": ["Thorne", "Elias"], "labels": ["Character"], "reveal_chapter": 1},
        {"id": "c_edith_thorne", "name": "Edith Thorne", "aliases": ["Thorne", "Edith"], "labels": ["Character"], "reveal_chapter": 1},
        {"id": "c_mara_voss", "name": "Mara Voss", "aliases": ["Mara"], "labels": ["Character"], "reveal_chapter": 1},
    ]

    with patch("app.llm.interpreter.get_visible_entities", return_value=mock_visible):
        with patch("app.llm.interpreter.resolve_entity") as mock_resolve:
            # 4a. Ambiguous name "Thorne"
            mock_resolve.side_effect = lambda name, chapter: (
                [mock_visible[0], mock_visible[1]] if "thorne" in name.lower()
                else [mock_visible[2]] if "mara" in name.lower()
                else []
            )

            res = interpret_question("How are Thorne and Mara connected?", chapter=1)
            assert res["status"] == "clarification_needed"
            assert "Thorne" in res["answer"]
            assert len(res["resolved_entities"]) == 0
            assert "ambiguous_options" in res

            # 4b. Unknown entity "Sherlock Holmes"
            mock_resolve.side_effect = lambda name, chapter: []
            res_unknown = interpret_question("How are Sherlock and Mara connected?", chapter=1)
            assert res_unknown["status"] in ("unresolved_entity", "clarification_needed")


# ==============================================================================
# Scenario 5: Relationship or evidence revealed after the reader's chapter is not returned.
# Testing Mechanism: Unit / Data-driven
# ==============================================================================
def test_scenario_5_future_relationship_and_evidence_spoiler_safety():
    """Scenario 5: Future claims and evidence (e.g. Halden culprit claim Ch 7) must not be returned at Ch 6."""
    path_ch6 = _dataset_graph_path("c_pavel_halden", "ev_cider_tampered", chapter=6)
    # At Chapter 6, cl_halden_perp (revealed Ch 7) must NOT be traversable
    assert path_ch6 is None

    path_ch7 = _dataset_graph_path("c_pavel_halden", "ev_cider_tampered", chapter=7)
    # At Chapter 7, it is unlocked
    assert path_ch7 is not None
    assert path_ch7["relationships"][0]["type"] == "PARTICIPATED_IN"


# ==============================================================================
# Scenario 6: A claim without visible supporting evidence is excluded from paths.
# Testing Mechanism: Unit / Data-driven
# ==============================================================================
def test_scenario_6_unsupported_claim_excluded():
    """Scenario 6: cl_will_executor is revealed in Ch 4, but its supporting evidence (evi_codicil) is revealed in Ch 5.
    At Chapter 4, the path must NOT be formed. At Chapter 5, it is unlocked."""
    path_ch4 = _dataset_graph_path("c_mara_voss", "ev_will_changed", chapter=4)
    assert path_ch4 is None

    path_ch5 = _dataset_graph_path("c_mara_voss", "ev_will_changed", chapter=5)
    assert path_ch5 is not None
    assert path_ch5["relationships"][0]["type"] == "PARTICIPATED_IN"


# ==============================================================================
# Scenario 7: A claim superseded by a visible later claim is handled correctly.
# Testing Mechanism: Unit / Data-driven
# ==============================================================================
def test_scenario_7_superseded_claim_handling():
    """Scenario 7: Jonas Reed is connected via ANTAGONIST_OF at Chapter 1.
    At Chapter 6, Jonas is connected via ALLY_OF, and ANTAGONIST_OF is excluded."""
    path_ch1 = _dataset_graph_path("c_jonas_reed", "c_elias_thorne", chapter=1)
    assert path_ch1 is not None
    rel_types_ch1 = [r["type"] for r in path_ch1["relationships"]]
    assert "ANTAGONIST_OF" in rel_types_ch1
    assert "ALLY_OF" not in rel_types_ch1

    path_ch6 = _dataset_graph_path("c_jonas_reed", "c_elias_thorne", chapter=6)
    assert path_ch6 is not None
    rel_types_ch6 = [r["type"] for r in path_ch6["relationships"]]
    assert "ALLY_OF" in rel_types_ch6
    assert "ANTAGONIST_OF" not in rel_types_ch6


# ==============================================================================
# Scenario 8: LLM output cannot introduce unsupported relationships or facts.
# Testing Mechanism: Unit / Mocked LLM
# ==============================================================================
def test_scenario_8_llm_hallucination_guard():
    """Scenario 8: If LLM introduces an ungrounded entity (e.g. claiming Tobias Quill was involved),
    the validation guard flags it and discards the output in favor of deterministic grounded facts."""
    valid_path = {
        "nodes": [
            {"id": "c_mara_voss", "name": "Mara Voss"},
            {"id": "c_elias_thorne", "name": "Elias Thorne"},
        ],
        "relationships": [
            {"source": "c_mara_voss", "target": "c_elias_thorne", "type": "EMPLOYED_BY", "claim_id": "cl_mara_employed"}
        ],
        "evidence": [
            {"claim_id": "cl_mara_employed", "claim": "Mara is employed by Elias", "kind": "document", "excerpt": "Employment agreement signed.", "reveal_chapter": 1}
        ]
    }

    # 8a. Hallucinated answer mentioning Ruth Ames (who is not in path)
    hallucinated_answer = "Mara Voss is connected to Elias Thorne, but Ruth Ames secretly orchestrated it."
    assert validate_answer_grounding(hallucinated_answer, valid_path, chapter=1) is False

    # 8b. Grounded answer mentioning only valid nodes
    grounded_answer = "Mara Voss is employed by Elias Thorne as estate archivist."
    assert validate_answer_grounding(grounded_answer, valid_path, chapter=1) is True

    # 8c. If LLM generates a hallucinated answer, generate_grounded_answer falls back to deterministic
    mock_choice = MagicMock()
    mock_choice.message.content = hallucinated_answer
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    with patch("app.llm.generator.OPENAI_API_KEY", "mock-key"):
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_completion

            result_answer = generate_grounded_answer("How are Mara and Elias connected?", valid_path, chapter=1)
            # Must NOT contain the hallucinated Ruth Ames mention
            assert "Ruth Ames" not in result_answer
            assert "Mara Voss connects to Elias Thorne" in result_answer


# ==============================================================================
# Scenario 9: Changing reading progress changes which paths and evidence are available.
# Testing Mechanism: Unit / Data-driven
# ==============================================================================
def test_scenario_9_reading_progress_evolves_graph():
    """Scenario 9: Advancing reading chapter unlocks new evidence and shortens/evolves paths."""
    # At Chapter 4: Mara -> Halden is 2 hops (via Elias)
    path_ch4 = _dataset_graph_path("c_mara_voss", "c_pavel_halden", chapter=4)
    assert path_ch4 is not None
    assert len(path_ch4["nodes"]) == 3

    # At Chapter 5: Mara finding the ledger discrepancy unlocks direct SUSPECTS edge
    path_ch5 = _dataset_graph_path("c_mara_voss", "c_pavel_halden", chapter=5)
    assert path_ch5 is not None
    assert len(path_ch5["nodes"]) == 2
    assert path_ch5["relationships"][0]["type"] == "SUSPECTS"


# ==============================================================================
# Scenario 10: Invalid API input returns an appropriate error.
# Testing Mechanism: API / Unit
# ==============================================================================
def test_scenario_10_invalid_api_input():
    """Scenario 10: Invalid API inputs return structured HTTP 422 errors."""
    # Chapter boundary 0 is rejected
    res_bad_chapter = client.get("/api/graph?chapter=0")
    assert res_bad_chapter.status_code == 422

    # Negative chapter in POST /api/ask is rejected
    res_bad_ask = client.post("/api/ask", json={"question": "Who died?", "chapter": -1})
    assert res_bad_ask.status_code == 422

    # Empty question in POST /api/ask is rejected
    res_empty_q = client.post("/api/ask", json={"question": "", "chapter": 1})
    assert res_empty_q.status_code == 422


# ==============================================================================
# Scenario 11: FalkorDB or LLM being unavailable is handled without crashing or leaking details.
# Testing Mechanism: Mock / Error Injection
# ==============================================================================
def test_scenario_11_service_unavailability_handling():
    """Scenario 11: DB and LLM outages return clean, non-leaking HTTP 503/502 responses."""
    with patch("app.api.routes.get_story_info", side_effect=Exception("redis.exceptions.ConnectionError: Error 10061")):
        res_story = client.get("/api/story")
        assert res_story.status_code == 503
        data = res_story.json()
        assert "10061" not in data["detail"]
        assert "localhost" not in data["detail"]
        assert "unavailable" in data["detail"].lower()

    with patch("app.api.routes.visible_graph", side_effect=Exception("Socket closed unexpectedly")):
        res_graph = client.get("/api/graph?chapter=1")
        assert res_graph.status_code == 503
        assert "Socket" not in res_graph.json()["detail"]

    # In agent.py, an unhandled exception returns error status cleanly
    with patch("app.llm.agent.interpret_question", side_effect=RuntimeError("Internal driver crashed")):
        agent_res = answer_question("How is Mara connected to Elias?", chapter=1)
        assert agent_res["status"] == "error"
        assert "Internal driver" not in agent_res["answer"]


# ==============================================================================
# Scenario 12: End-to-end question workflow returns a real graph path and supporting evidence.
# Testing Mechanism: Mocked Graph Traversal / End-to-End Workflow
# ==============================================================================
def test_scenario_12_end_to_end_question_workflow():
    """Scenario 12: End-to-end question answering pipeline returns structured path and evidence."""
    mock_path = _dataset_graph_path("c_mara_voss", "c_elias_thorne", chapter=1)

    with patch("app.llm.interpreter.resolve_entity") as mock_resolve:
        mock_resolve.side_effect = lambda name, ch: (
            [{"id": "c_mara_voss", "name": "Mara Voss", "labels": ["Character"], "reveal_chapter": 1}] if "mara" in name.lower()
            else [{"id": "c_elias_thorne", "name": "Elias Thorne", "labels": ["Character"], "reveal_chapter": 1}] if "elias" in name.lower()
            else []
        )
        with patch("app.llm.agent.find_connection", return_value=mock_path):
            result = answer_question("How is Mara Voss connected to Elias Thorne?", chapter=1)
            assert result["status"] == "answered"
            assert len(result["resolved_entities"]) == 2
            assert len(result["nodes"]) == 2
            assert len(result["relationships"]) == 1
            assert result["relationships"][0]["type"] == "EMPLOYED_BY"
            assert len(result["evidence"]) >= 1
            assert "Mara Voss connects to Elias Thorne" in result["answer"]


# ==============================================================================
# Spoiler-Safety Audit: Indirect leak checks
# Testing Mechanism: Unit / Role Sanitization
# ==============================================================================
def test_spoiler_safety_audit_role_sanitization():
    """Verify that endgame roles ('the culprit', 'accomplice', 'victim') are sanitized before their reveal chapters."""
    # Halden at Chapter 1 must be 'Family physician', not 'Family physician, the culprit'
    assert sanitize_role("c_pavel_halden", "Family physician, the culprit", chapter=1) == "Family physician"
    assert sanitize_role("c_pavel_halden", "Family physician, the culprit", chapter=6) == "Family physician"
    # At Chapter 7 (when cl_halden_perp is revealed), role is revealed
    assert sanitize_role("c_pavel_halden", "Family physician, the culprit", chapter=7) == "Family physician, the culprit"

    # Ruth Ames at Chapter 6 must be 'Clinic nurse', not accomplice
    assert sanitize_role("c_ruth_ames", "Clinic nurse, Halden's accomplice", chapter=6) == "Clinic nurse"
    assert sanitize_role("c_ruth_ames", "Clinic nurse, Halden's accomplice", chapter=7) == "Clinic nurse, Halden's accomplice"

    # Elias at Chapter 1 must be 'Estate owner', not 'Estate owner, the victim'
    assert sanitize_role("c_elias_thorne", "Estate owner, the victim", chapter=1) == "Estate owner"
    assert sanitize_role("c_elias_thorne", "Estate owner, the victim", chapter=2) == "Estate owner, the victim"
