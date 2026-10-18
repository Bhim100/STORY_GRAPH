"""Unit and integration tests for event and evidence retrieval using controlled FalkorDB query templates."""
import pytest
from starlette.testclient import TestClient

from app.db import ping
from app.llm.agent import answer_question
from app.llm.router import QuestionType, route_question
from app.main import app

client = TestClient(app)
requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


@requires_falkordb
def test_greenhouse_event_chapter_1_vs_chapter_2():
    """Verify Greenhouse event retrieval at Chapter 1 vs Chapter 2.
    
    Chapter 1: Elias's death has not yet occurred/been revealed; answer reports no events at The Greenhouse.
    Chapter 2: Elias's death event is revealed and appears with supporting death scene evidence.
    """
    # 1. Chapter 1: Death is absent
    res_ch1 = answer_question("What happened at the greenhouse?", chapter=1)
    assert res_ch1["status"] == "event_evidence"
    assert res_ch1["question_type"] == QuestionType.EVENT_EVIDENCE
    assert "no events are established" in res_ch1["answer"] or "no recorded events" in res_ch1["answer"]
    assert "dead" not in res_ch1["answer"].lower()
    assert "murder" not in res_ch1["answer"].lower()
    assert len(res_ch1["events"]) == 0

    # 2. Chapter 2: Elias's death appears with scene evidence
    res_ch2 = answer_question("What happened at the greenhouse?", chapter=2)
    assert res_ch2["status"] == "event_evidence"
    assert res_ch2["question_type"] == QuestionType.EVENT_EVIDENCE
    assert len(res_ch2["events"]) >= 1
    event_ids = [ev["id"] for ev in res_ch2["events"]]
    assert "ev_elias_death" in event_ids

    # Claim and evidence validation
    ans_ch2 = res_ch2["answer"]
    assert "[Confirmed]" in ans_ch2
    assert "greenhouse" in ans_ch2.lower()
    assert any("broken glass" in e.get("excerpt", "").lower() for e in res_ch2["evidence"])


@requires_falkordb
def test_jonas_allegation_chapter_1():
    """Verify 'Why was Jonas suspected?' at Chapter 1 returns Edith's testimony clearly labeled as an allegation.
    
    An allegation must never be presented as a proven fact or confirmed murder.
    """
    res = answer_question("Why was Jonas suspected?", chapter=1)
    assert res["status"] == "event_evidence"
    assert res["question_type"] == QuestionType.EVENT_EVIDENCE

    ans = res["answer"]
    # Check that allegation tag and disclaimer are present
    assert "[Allegation]" in ans
    assert "unproven allegation" in ans.lower() or "early lead" in ans.lower()
    assert "not a confirmed crime" in ans.lower()

    # Confirm it does not state Jonas committed murder
    assert "confirmed murder" not in ans.lower()

    # Check evidence attachment
    assert len(res["evidence"]) >= 1
    evidence_ids = [e["evidence_id"] for e in res["evidence"]]
    assert "evi_witness_edith" in evidence_ids
    assert any("Edith states" in e.get("excerpt", "") for e in res["evidence"])

    # Check claim structure
    assert len(res["claims"]) >= 1
    allegation_claim = next((c for c in res["claims"] if c.get("id") == "cl_jonas_antagonist"), None)
    assert allegation_claim is not None
    assert allegation_claim["validation"] == "alleged"


@requires_falkordb
def test_halden_evidence_before_and_after_reveal_chapter():
    """Verify evidence implicating Halden before (Ch. 4) and after (Ch. 7) its reveal chapter.
    
    Chapter 4: No incriminating evidence or perpetrator claims are revealed (only innocent physician card).
    Chapter 7: Incriminating vial and lethal cider causality are revealed and returned.
    """
    # 1. Chapter 4: Safe, no perpetrator evidence
    res_ch4 = answer_question("What evidence connects Halden to the death?", chapter=4)
    assert res_ch4["status"] == "event_evidence"
    ans_ch4 = res_ch4["answer"]
    assert "no revealed evidence or claims in the story graph implicate" in ans_ch4
    assert "vial" not in ans_ch4.lower()
    assert "aconite" not in ans_ch4.lower()
    assert "perpetrator" not in ans_ch4.lower()
    assert "tampered" not in ans_ch4.lower()

    # Check no incriminating evidence in structured payload
    assert not any(e["evidence_id"] == "evi_vial" for e in res_ch4["evidence"])

    # 2. Chapter 7: Incriminating evidence visible
    res_ch7 = answer_question("What evidence connects Halden to the death?", chapter=7)
    assert res_ch7["status"] == "event_evidence"
    ans_ch7 = res_ch7["answer"]
    assert "Dr. Pavel Halden" in ans_ch7
    assert "[Confirmed]" in ans_ch7
    assert "vial" in ans_ch7.lower()

    # Check structured evidence includes vial and toxicology
    evidence_ids = [e["evidence_id"] for e in res_ch7["evidence"]]
    assert "evi_vial" in evidence_ids
    assert any("medical bag" in e.get("excerpt", "").lower() for e in res_ch7["evidence"])


@requires_falkordb
def test_claim_with_no_visible_supporting_evidence():
    """Verify a claim revealed before its supporting evidence reports a data gap instead of guessing."""
    # At Chapter 4, ev_will_changed is revealed and cl_will_executor is revealed,
    # but supporting evidence evi_codicil is only revealed in Chapter 5.
    res = answer_question("What happened regarding the will?", chapter=4)
    assert res["status"] == "event_evidence"

    ans = res["answer"]
    assert "[Unverified]" in ans
    assert "Data Gap: No supporting evidence is visible at Chapter 4." in ans
    assert "Elias names Mara as executor" in ans or "Elias named Mara executor" in ans

    # Evidence list at chapter 4 should be empty for this claim
    assert len(res["evidence"]) == 0
    assert len(res["claims"]) == 1
    assert len(res["claims"][0]["evidence"]) == 0


@requires_falkordb
def test_no_results_handling():
    """Verify querying an entity or location with no events/evidence returns a clean no-results response."""
    # Location with no events
    res_loc = answer_question("What happened at the harbor inn?", chapter=2)
    assert res_loc["status"] == "event_evidence"
    assert "no events are established or revealed to have occurred at The Harbor Inn" in res_loc["answer"]
    assert len(res_loc["events"]) == 0

    # Character with no implicating evidence
    res_char = answer_question("What evidence implicates Tobias Quill?", chapter=2)
    assert res_char["status"] == "event_evidence"
    assert "no revealed evidence or claims in the story graph implicate Tobias Quill" in res_char["answer"]
    assert len(res_char["evidence"]) == 0


@requires_falkordb
def test_api_ask_event_evidence_greenhouse_chapter_2():
    """Integration test: Verify /api/ask HTTP endpoint returns event_evidence payload."""
    res = client.post("/api/ask", json={
        "question": "What happened at the greenhouse?",
        "chapter": 2,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "event_evidence"
    assert data["question_type"] == "event_evidence"
    assert "Elias is found dead in the greenhouse" in data["answer"]
    assert len(data["events"]) >= 1
    assert len(data["evidence"]) >= 1
