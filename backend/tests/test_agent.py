"""Unit and integration tests for Phase 3: AI Agent & Spoiler Boundary Engine."""
from unittest.mock import MagicMock, patch
import pytest
from app.db import ping
from app.graph.explorer import find_connection, resolve_entity
from app.llm.agent import answer_question
from app.llm.generator import generate_grounded_answer
from app.llm.interpreter import interpret_question

requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


@requires_falkordb
def test_resolve_entity_visible_and_hidden():
    """Verify entity visibility adheres strictly to chapter boundaries."""
    # Ruth Ames is revealed in Chapter 6
    assert resolve_entity("Ruth Ames", chapter=5) == []
    ruth_ch6 = resolve_entity("Ruth Ames", chapter=6)
    assert len(ruth_ch6) == 1
    assert ruth_ch6[0]["id"] == "c_ruth_ames"

    # Elias Thorne is revealed in Chapter 1
    elias = resolve_entity("Elias Thorne", chapter=1)
    assert len(elias) == 1
    assert elias[0]["id"] == "c_elias_thorne"

    # Alias matching: 'Dr. Halden' and 'Halden' match Pavel Halden
    halden_alias = resolve_entity("Dr. Halden", chapter=1)
    assert len(halden_alias) == 1
    assert halden_alias[0]["id"] == "c_pavel_halden"


@requires_falkordb
def test_ambiguous_entity_resolution():
    """Verify that ambiguous entity names require clarification with visible options only."""
    res = answer_question("How are Thorne and Mara connected?", chapter=1)
    assert res["status"] == "clarification_needed"
    assert "Thorne" in res["answer"]
    # Check that both Elias and Edith are surfaced as candidates
    assert "Elias Thorne" in res["answer"]
    assert "Edith Thorne" in res["answer"]
    assert res["path"] is None


@requires_falkordb
def test_hidden_entity_resolution_no_leak():
    """Verify that asking about a hidden character returns unresolved_entity with 0 leak."""
    res = answer_question("How is Ruth Ames connected to Halden?", chapter=5)
    assert res["status"] == "unresolved_entity"
    assert "Ruth Ames" in res["answer"]
    # Must NOT disclose her role, accomplice status, or future chapter 6 reveal
    assert "accomplice" not in res["answer"].lower()
    assert "chapter 6" not in res["answer"].lower()
    assert res["path"] is None


@requires_falkordb
def test_direct_connection_at_chapter_1():
    """Verify Mara -> Elias direct connection is found and backed by evidence."""
    res = answer_question("How is Mara Voss connected to Elias Thorne?", chapter=1)
    assert res["status"] == "answered"
    assert len(res["resolved_entities"]) == 2
    assert len(res["nodes"]) == 2
    assert len(res["relationships"]) == 1
    assert res["relationships"][0]["type"] == "EMPLOYED_BY"
    assert len(res["evidence"]) >= 1
    assert res["evidence"][0]["reveal_chapter"] <= 1
    assert "contract" in res["evidence"][0]["excerpt"].lower() or "employment" in res["evidence"][0]["excerpt"].lower()


@requires_falkordb
def test_multi_hop_route_evolution():
    """Verify Mara <-> Halden path shifts from 2 hops (via Elias) at Ch 4 to direct (SUSPECTS) at Ch 5."""
    # At Chapter 4: Only indirect route through Elias exists
    path_ch4 = find_connection("c_mara_voss", "c_pavel_halden", chapter=4)
    assert path_ch4 is not None
    node_ids_ch4 = [n["id"] for n in path_ch4["nodes"]]
    assert node_ids_ch4 == ["c_mara_voss", "c_elias_thorne", "c_pavel_halden"]

    # At Chapter 5: Direct SUSPECTS edge is unlocked by Mara finding the discrepancy
    path_ch5 = find_connection("c_mara_voss", "c_pavel_halden", chapter=5)
    assert path_ch5 is not None
    node_ids_ch5 = [n["id"] for n in path_ch5["nodes"]]
    assert node_ids_ch5 == ["c_mara_voss", "c_pavel_halden"]
    assert path_ch5["relationships"][0]["type"] == "SUSPECTS"


@requires_falkordb
def test_isolated_entity_no_path():
    """Verify Tobias Quill has no path to household members at any chapter."""
    res_ch2 = answer_question("How is Tobias Quill connected to Elias Thorne?", chapter=2)
    assert res_ch2["status"] == "no_path"
    assert "does not establish a supported connection" in res_ch2["answer"]

    res_ch8 = answer_question("How is Tobias Quill connected to Elias Thorne?", chapter=8)
    assert res_ch8["status"] == "no_path"


@requires_falkordb
def test_unverified_claim_excluded():
    """Verify cl_will_executor (revealed Ch 4, evidence Ch 5) is untraversable at Ch 4."""
    # At Chapter 4, evidence is not yet revealed, so connection to the will changed event cannot be formed
    path_ch4 = find_connection("c_mara_voss", "ev_will_changed", chapter=4)
    assert path_ch4 is None

    # At Chapter 5, evi_codicil is revealed, so connection is valid
    path_ch5 = find_connection("c_mara_voss", "ev_will_changed", chapter=5)
    assert path_ch5 is not None
    assert path_ch5["relationships"][0]["type"] == "PARTICIPATED_IN"


@requires_falkordb
def test_superseded_claim_exclusion():
    """Verify Jonas Reed antagonist claim is active at Ch 1 but superseded at Ch 6."""
    path_ch1 = find_connection("c_jonas_reed", "c_elias_thorne", chapter=1)
    assert path_ch1 is not None
    # At Ch 1, Jonas is connected via ANTAGONIST_OF
    rel_types_ch1 = [r["type"] for r in path_ch1["relationships"]]
    assert "ANTAGONIST_OF" in rel_types_ch1

    # At Ch 6, Jonas is connected via ALLY_OF
    path_ch6 = find_connection("c_jonas_reed", "c_elias_thorne", chapter=6)
    assert path_ch6 is not None
    rel_types_ch6 = [r["type"] for r in path_ch6["relationships"]]
    assert "ALLY_OF" in rel_types_ch6
    assert "ANTAGONIST_OF" not in rel_types_ch6


@requires_falkordb
def test_mock_llm_interpretation_and_generation():
    """Verify agent functions correctly when OpenAI client is mocked."""
    # Mock LLM entity selection tool call
    mock_choice = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.function.arguments = '{"entity_a": "Mara Voss", "entity_b": "Elias Thorne"}'
    mock_choice.message.tool_calls = [mock_tool_call]

    mock_completion_select = MagicMock()
    mock_completion_select.choices = [mock_choice]

    # Mock LLM grounded answer completion
    mock_choice_answer = MagicMock()
    mock_choice_answer.message.content = "Mara Voss is employed as estate archivist by Elias Thorne as evidenced by the contract in Chapter 1."
    mock_completion_answer = MagicMock()
    mock_completion_answer.choices = [mock_choice_answer]

    with patch("app.llm.interpreter.OPENAI_API_KEY", "mock-key"):
        with patch("app.llm.generator.OPENAI_API_KEY", "mock-key"):
            with patch("openai.OpenAI") as mock_openai_cls:
                mock_client = MagicMock()
                mock_openai_cls.return_value = mock_client
                mock_client.chat.completions.create.side_effect = [
                    mock_completion_select,
                    mock_completion_answer,
                ]

                res = answer_question("Explain the link between Mara and Elias Thorne", chapter=1)
                assert res["status"] == "answered"
                assert "Mara Voss is employed" in res["answer"]
                assert len(res["relationships"]) == 1


def test_invalid_chapter_boundary():
    """Verify that chapter <= 0 returns an error status."""
    res = answer_question("How is Mara connected to Elias?", chapter=0)
    assert res["status"] == "error"
    assert "positive integer" in res["answer"]
