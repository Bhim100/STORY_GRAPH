"""Unit and integration tests for the deterministic question router and extended question engine."""
import pytest
from app.db import ping
from app.llm.agent import answer_question
from app.llm.router import QuestionType, route_question

requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


@requires_falkordb
def test_route_connection_query():
    """Verify connection questions between two entities are routed to QuestionType.CONNECTION."""
    # Classic two-entity connection
    r1 = route_question("How are Mara Voss and Jonas Reed connected?", chapter=1)
    assert r1["question_type"] == QuestionType.CONNECTION
    assert r1["status"] == "ok"
    assert len(r1["resolved_entities"]) == 2
    ids1 = [e["id"] for e in r1["resolved_entities"]]
    assert "c_mara_voss" in ids1
    assert "c_jonas_reed" in ids1

    # Alternative connection phrasing
    r2 = route_question("What is the relationship between Mara Voss and Dr. Halden?", chapter=1)
    assert r2["question_type"] == QuestionType.CONNECTION
    assert r2["status"] == "ok"

    r3 = route_question("Is Tobias Quill connected to the household?", chapter=2)
    assert r3["question_type"] == QuestionType.CONNECTION


@requires_falkordb
def test_route_entity_profile_query():
    """Verify single-entity profile queries are routed to QuestionType.ENTITY_PROFILE."""
    r1 = route_question("Tell me about Mara Voss", chapter=1)
    assert r1["question_type"] == QuestionType.ENTITY_PROFILE
    assert r1["status"] == "ok"
    assert len(r1["resolved_entities"]) == 1
    assert r1["resolved_entities"][0]["id"] == "c_mara_voss"

    r2 = route_question("Who is Jonas Reed?", chapter=1)
    assert r2["question_type"] == QuestionType.ENTITY_PROFILE
    assert r2["status"] == "ok"
    assert r2["resolved_entities"][0]["id"] == "c_jonas_reed"

    r3 = route_question("Describe Dr. Halden", chapter=1)
    assert r3["question_type"] == QuestionType.ENTITY_PROFILE
    assert r3["status"] == "ok"
    assert r3["resolved_entities"][0]["id"] == "c_pavel_halden"

    r4 = route_question("What do we know about Elias Thorne?", chapter=1)
    assert r4["question_type"] == QuestionType.ENTITY_PROFILE
    assert r4["status"] == "ok"


@requires_falkordb
def test_route_collection_query():
    """Verify list and collection queries are routed to QuestionType.COLLECTION_QUERY."""
    r1 = route_question("List all characters", chapter=1)
    assert r1["question_type"] == QuestionType.COLLECTION_QUERY
    assert r1["status"] == "ok"

    r2 = route_question("List all suspects", chapter=1)
    assert r2["question_type"] == QuestionType.COLLECTION_QUERY
    assert r2["status"] == "ok"

    r3 = route_question("Who are the members of Thorne Household?", chapter=1)
    assert r3["question_type"] == QuestionType.COLLECTION_QUERY
    assert r3["status"] == "ok"

    r4 = route_question("Show all locations", chapter=1)
    assert r4["question_type"] == QuestionType.COLLECTION_QUERY
    assert r4["status"] == "ok"


@requires_falkordb
def test_route_event_evidence_query():
    """Verify event and evidence queries are routed to QuestionType.EVENT_EVIDENCE."""
    r1 = route_question("What happened at the harvest dinner?", chapter=1)
    assert r1["question_type"] == QuestionType.EVENT_EVIDENCE
    assert r1["status"] == "ok"

    r2 = route_question("What evidence was found in the greenhouse?", chapter=1)
    assert r2["question_type"] == QuestionType.EVENT_EVIDENCE
    assert r2["status"] == "ok"

    r3 = route_question("Where did Elias die?", chapter=2)
    assert r3["question_type"] == QuestionType.EVENT_EVIDENCE
    assert r3["status"] == "ok"


@requires_falkordb
def test_route_culprit_query():
    """Verify culprit and 'who did it?' queries are routed to QuestionType.CULPRIT_QUERY."""
    r1 = route_question("Who killed Elias Thorne?", chapter=1)
    assert r1["question_type"] == QuestionType.CULPRIT_QUERY
    assert r1["status"] == "ok"

    r2 = route_question("Who is the culprit?", chapter=1)
    assert r2["question_type"] == QuestionType.CULPRIT_QUERY
    assert r2["status"] == "ok"

    r3 = route_question("Who poisoned the cider?", chapter=1)
    assert r3["question_type"] == QuestionType.CULPRIT_QUERY
    assert r3["status"] == "ok"

    r4 = route_question("Who did it?", chapter=1)
    assert r4["question_type"] == QuestionType.CULPRIT_QUERY
    assert r4["status"] == "ok"


def test_route_unsupported_unrelated_queries():
    """Verify unrelated questions are identified as QuestionType.UNSUPPORTED without hitting FalkorDB."""
    r1 = route_question("What is the capital of France?", chapter=1)
    assert r1["question_type"] == QuestionType.UNSUPPORTED
    assert r1["status"] == "unsupported"
    assert "cannot answer this question from the supported graph operations" in r1["answer"]

    r2 = route_question("How do I bake a chocolate cake?", chapter=1)
    assert r2["question_type"] == QuestionType.UNSUPPORTED
    assert r2["status"] == "unsupported"

    r3 = route_question("Tell me a funny joke", chapter=1)
    assert r3["question_type"] == QuestionType.UNSUPPORTED
    assert r3["status"] == "unsupported"


@requires_falkordb
def test_ambiguous_name_clarification_in_routing():
    """Verify ambiguous names return clarification_needed with disambiguation options."""
    # Single entity profile query with ambiguous name "Thorne"
    r = route_question("Tell me about Thorne", chapter=1)
    assert r["status"] == "clarification_needed"
    assert len(r["ambiguous_options"]) >= 2
    option_names = [opt["name"] for opt in r["ambiguous_options"]]
    assert "Elias Thorne" in option_names
    assert "Edith Thorne" in option_names

    # Agent level response
    res = answer_question("Tell me about Thorne", chapter=1)
    assert res["status"] == "clarification_needed"
    assert "Thorne" in res["answer"]
    assert "Elias Thorne" in res["answer"]
    assert "Edith Thorne" in res["answer"]


@requires_falkordb
def test_hidden_entity_at_chapter_boundary():
    """Verify entities revealed in later chapters are treated as unresolved with zero spoiler leaks."""
    # Ruth Ames is revealed in Chapter 6
    r = route_question("Tell me about Ruth Ames", chapter=1)
    assert r["status"] == "unresolved_entity"
    assert "Ruth Ames" in r["unresolved_entities"]

    res = answer_question("Tell me about Ruth Ames", chapter=1)
    assert res["status"] == "unresolved_entity"
    assert "Ruth Ames" in res["answer"]
    assert "accomplice" not in res["answer"].lower()
    assert "chapter 6" not in res["answer"].lower()


@requires_falkordb
def test_answer_question_preserves_connection_behavior():
    """Verify that existing two-entity connection questions still find graph paths and evidence."""
    res = answer_question("How are Mara Voss and Jonas Reed connected?", chapter=1)
    assert res["status"] == "answered"
    assert res["question_type"] == QuestionType.CONNECTION
    assert res["path"] is not None
    assert len(res["nodes"]) >= 2
    assert len(res["relationships"]) >= 1
    assert len(res["evidence"]) >= 1
    assert "Mara Voss" in res["answer"]
    assert "Jonas Reed" in res["answer"]


@requires_falkordb
def test_answer_question_entity_profile_dispatch():
    """Verify 'Tell me about Mara Voss' routes to the entity-profile handler returning grounded profile data."""
    res = answer_question("Tell me about Mara Voss", chapter=1)
    assert res["status"] == "entity_profile"
    assert res["question_type"] == QuestionType.ENTITY_PROFILE
    assert len(res["resolved_entities"]) == 1
    assert res["resolved_entities"][0]["name"] == "Mara Voss"
    assert res["resolved_entities"][0]["role"] == "Estate archivist"
    assert res["path"] is None

    # Verify visible relationships and evidence
    ans = res["answer"]
    assert "Mara Voss" in ans
    assert "Estate archivist" in ans
    assert "EMPLOYED_BY" in ans
    assert "Elias Thorne" in ans
    assert "Employment agreement" in ans
    assert len(res["relationships"]) >= 1
    assert len(res["evidence"]) >= 1


@requires_falkordb
def test_entity_profile_dr_halden_no_culprit_leak_chapter_1():
    """Verify Dr. Halden's profile at Chapter 1 returns safe physician role and zero culprit/endgame leaks."""
    res = answer_question("Describe Dr. Halden", chapter=1)
    assert res["status"] == "entity_profile"
    assert res["question_type"] == QuestionType.ENTITY_PROFILE
    assert len(res["resolved_entities"]) == 1
    node = res["resolved_entities"][0]
    assert node["name"] == "Dr. Pavel Halden"
    assert node["role"] == "Family physician"
    assert "culprit" not in node["role"].lower()

    ans = res["answer"]
    assert "Dr. Pavel Halden" in ans
    assert "Family physician" in ans
    assert "PHYSICIAN_OF" in ans
    assert "Elias Thorne" in ans
    assert "Official appointment card" in ans

    # Ensure zero leak of future facts
    assert "culprit" not in ans.lower()
    assert "poison" not in ans.lower()
    assert "tamper" not in ans.lower()
    assert "perpetrator" not in ans.lower()
    assert "ruth ames" not in ans.lower()


@requires_falkordb
def test_collection_query_thorne_household_members():
    """Verify 'Who is in the Thorne household?' returns verified members with evidence and documents unverified claims."""
    res = answer_question("Who is in the Thorne household?", chapter=1)
    assert res["status"] == "collection_query"
    assert res["question_type"] == QuestionType.COLLECTION_QUERY
    # Only Jonas Reed has direct supporting evidence for household membership
    assert len(res["members"]) == 1
    assert res["members"][0]["name"] == "Jonas Reed"
    assert res["members"][0]["role"] == "Groundskeeper"
    assert res["members"][0]["relationship"] == "MEMBER_OF"

    # Supporting evidence
    assert len(res["evidence"]) == 1
    assert res["evidence"][0]["evidence_id"] == "evi_grounds_log"
    assert "resident caretaker" in res["evidence"][0]["excerpt"]

    # Check that unverified membership claims are tracked and reported
    ans = res["answer"]
    assert "Jonas Reed" in ans
    assert "resident caretaker" in ans
    assert "Note: Unverified membership claims exist" in ans
    assert "Edith Thorne" in ans
    assert "Elias Thorne" in ans
    assert "Ines Calloway" in ans
    assert "Mara Voss" in ans



@requires_falkordb
def test_collection_query_thorne_manor_distinction():
    """Verify asking about Thorne Manor explicitly states distinction with household membership without assuming residence."""
    res = answer_question("Who lives at Thorne Manor?", chapter=1)
    assert res["status"] == "collection_query"
    assert res["question_type"] == QuestionType.COLLECTION_QUERY
    # No direct residence nodes in graph
    assert len(res["nodes"]) == 0
    assert len(res["members"]) == 0

    ans = res["answer"]
    assert "does not establish supported residence or employment relationships" in ans
    assert "Thorne Manor" in ans
    assert "household membership is not established as physical residence" in ans
    assert "harvest dinner" in ans


@requires_falkordb
def test_chapter_filtering_for_entities_and_factions():
    """Verify server-side chapter filtering prevents visibility of unrevealed characters, claims, and factions."""
    # Tobias Quill is revealed in Chapter 2, not Chapter 1
    ch1_res = answer_question("Who is Tobias Quill?", chapter=1)
    assert ch1_res["status"] == "unresolved_entity"
    assert "not identified" in ch1_res["answer"] or "could not identify" in ch1_res["answer"]

    ch2_res = answer_question("Who is Tobias Quill?", chapter=2)
    assert ch2_res["status"] == "entity_profile"
    assert ch2_res["resolved_entities"][0]["name"] == "Tobias Quill"
    assert ch2_res["resolved_entities"][0]["role"] == "Travelling seed merchant"
    assert "Harbor Merchant Guild" in ch2_res["answer"]
    assert "MEMBER_OF" in ch2_res["answer"]

    # Faction filtering: Harbor Merchant Guild is revealed in Chapter 2, not Chapter 1
    fac1_res = answer_question("Who is in the Harbor Merchant Guild?", chapter=1)
    assert fac1_res["status"] == "unresolved_entity"
    assert "could not identify" in fac1_res["answer"].lower()

    fac2_res = answer_question("Who is in the Harbor Merchant Guild?", chapter=2)
    assert fac2_res["status"] == "collection_query"
    assert len(fac2_res["members"]) == 1
    assert fac2_res["members"][0]["name"] == "Tobias Quill"
    assert "Harbor Merchant Guild membership registry" in fac2_res["answer"]


def test_answer_question_unsupported_rejection():
    """Verify unrelated questions return unsupported response rather than inventing answers."""
    res = answer_question("What is the capital of France?", chapter=1)
    assert res["status"] == "unsupported_question"
    assert res["question_type"] == QuestionType.UNSUPPORTED
    assert "cannot answer this question from the supported graph operations" in res["answer"]
    assert res["path"] is None


@requires_falkordb
def test_answer_question_culprit_dispatch():
    """Verify culprit questions route to culprit handler and state facts are not established."""
    res = answer_question("Who killed Elias Thorne?", chapter=1)
    assert res["status"] == "culprit_query"
    assert res["question_type"] == QuestionType.CULPRIT_QUERY
    assert "culprit" in res["answer"].lower()
    assert "not established by available graph data" in res["answer"]
    assert res["path"] is None

