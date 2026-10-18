"""Tests for LLM-assisted knowledge graph extraction, exact quote validation, spoiler tracking, and safe fallbacks."""
import pytest
from unittest.mock import MagicMock, patch

from app.db import ping, current_graph_name
from app.graph.explorer import visible_graph, get_node_details, resolve_entity
from app.graph.seed import seed_story_to_falkordb
from app.llm.extractor import (
    EntityRegistry,
    ExtractionPipelineResult,
    are_names_same_person,
    run_story_extraction_pipeline,
    verify_excerpt_in_text,
)

requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


# ============================================================================
# 1. Exact Quote Verification & Rejection of Hallucinated Quotes
# ============================================================================

def test_exact_quote_verification_accepts_verbatim():
    """Verify that exact substrings and normalized quotes from the manuscript are accepted."""
    chapter_text = (
        "Inspector Gregory was one of the smartest officers in the provincial constabulary. "
        "Colonel Ross was the fortunate owner of Silver Blaze, the favorite for the Wessex Cup."
    )

    # 1. Exact substring
    valid, reason = verify_excerpt_in_text(
        "Colonel Ross was the fortunate owner of Silver Blaze",
        chapter_text,
    )
    assert valid is True
    assert "verbatim" in reason.lower()

    # 2. Normalized whitespace & quote marks
    valid, reason = verify_excerpt_in_text(
        "\"Inspector Gregory was one of the smartest officers\"",
        chapter_text,
    )
    assert valid is True

    # 3. Trimmed punctuation
    valid, reason = verify_excerpt_in_text(
        "fortunate owner of Silver Blaze,",
        chapter_text,
    )
    assert valid is True


def test_exact_quote_verification_rejects_hallucinations_and_paraphrases():
    """Verify that hallucinated, paraphrased, or fabricated quotes are strictly rejected."""
    chapter_text = (
        "Inspector Gregory was one of the smartest officers in the provincial constabulary. "
        "Colonel Ross was the fortunate owner of Silver Blaze."
    )

    # 1. Paraphrased statement (not in text)
    valid, reason = verify_excerpt_in_text(
        "Colonel Ross bought the horse Silver Blaze for a lot of money.",
        chapter_text,
    )
    assert valid is False
    assert "not found" in reason.lower()

    # 2. Completely fabricated quote
    valid, reason = verify_excerpt_in_text(
        "Gregory told Holmes that the butler did it in the library.",
        chapter_text,
    )
    assert valid is False
    assert "not found" in reason.lower()

    # 3. Empty or trivial excerpt
    valid, reason = verify_excerpt_in_text("", chapter_text)
    assert valid is False

    valid, reason = verify_excerpt_in_text("the", chapter_text)
    assert valid is False


# ============================================================================
# 2. Claim Validation & Guilt Rules
# ============================================================================

def test_guilt_rule_prevents_treating_suspicion_as_proof():
    """Verify that accusations or suspicions are never assigned COMMITTED predicate."""
    chapter = [{
        "chapter_number": 1,
        "title": "Chapter 1",
        "content": "Inspector Gregory has arrested Fitzroy Simpson as the prime suspect in the disappearance.",
    }]

    # Mock LLM returning COMMITTED for an arrested suspect
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """
    {
      "characters": [
        {"name": "Inspector Gregory", "role": "Police Inspector", "aliases": ["Gregory"]},
        {"name": "Fitzroy Simpson", "role": "Arrested Suspect", "aliases": ["Simpson"]}
      ],
      "locations": [],
      "factions": [],
      "events": [
        {
          "title": "Arrest of Fitzroy Simpson",
          "occurrence_chapter": 1,
          "reveal_chapter": 1,
          "participants": [{"character_name": "Fitzroy Simpson", "role": "suspect"}]
        }
      ],
      "claims": [
        {
          "subject_name": "Fitzroy Simpson",
          "predicate": "COMMITTED",
          "object_name": "Arrest of Fitzroy Simpson",
          "text": "Simpson committed the crime.",
          "validation": "suspected",
          "reveal_chapter": 1,
          "excerpt": "Inspector Gregory has arrested Fitzroy Simpson as the prime suspect"
        }
      ]
    }
    """

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("app.llm.extractor.get_llm_client", return_value=(mock_client, "mock-model")):
        res = run_story_extraction_pipeline(
            title="Test Mystery",
            author="Author",
            description="",
            chapters_data=chapter,
            book_id="test_guilt_rules",
        )

    claims = res.dataset.claims
    assert len(claims) >= 1
    # Check that COMMITTED with validation 'suspected' was converted to SUSPECTS
    simpson_claim = next((c for c in claims if c.kind != "PARTICIPATED_IN" and ("simpson" in c.subject.lower() or "simpson" in c.object.lower())), None)
    assert simpson_claim is not None
    assert simpson_claim.kind != "COMMITTED"
    assert simpson_claim.kind == "SUSPECTS"
    assert simpson_claim.validation in ("suspected", "alleged")


# ============================================================================
# 3. Chapter Fields & Spoiler Filtering
# ============================================================================

def test_chapter_fields_and_spoiler_filtering():
    """Verify that reveal_chapter hides later plot points from early chapter graph boundaries."""
    registry = EntityRegistry(book_id="test_spoilers")

    # Character introduced in Ch 1
    c1 = registry.register_character("Sherlock Holmes", "Detective", ["Holmes"], chapter_num=1)
    # Character introduced in Ch 3
    c3 = registry.register_character("Silas Brown", "Trainer", ["Brown"], chapter_num=3)

    assert registry.characters[c1].reveal_chapter == 1
    assert registry.characters[c3].reveal_chapter == 3

    # Event occurring in Ch 1, revealed in Ch 3
    ev_id = registry.register_event("Secret Stabling", occurrence_ch=1, reveal_ch=3)
    assert registry.events[ev_id].event_chapter == 1
    assert registry.events[ev_id].reveal_chapter == 3


# ============================================================================
# 4. Conservative Alias Resolution vs Distinct Ambiguous Entities
# ============================================================================

def test_conservative_alias_resolution():
    """Verify that honorific variants merge safely while different persons (spouses) are kept separate."""
    # Same person: Dr. John Watson and Watson
    assert are_names_same_person("Dr. John Watson", "Watson") is True
    assert are_names_same_person("Mr. Sherlock Holmes", "Sherlock Holmes") is True
    assert are_names_same_person("Inspector Gregory", "Gregory") is True

    # Different people: Mrs. Straker and John Straker must NEVER merge
    assert are_names_same_person("Mrs. Straker", "John Straker") is False
    assert are_names_same_person("Mrs. Straker", "Mr. John Straker") is False
    assert are_names_same_person("Lady Eleanor", "Lord Harrington") is False

    # Registry test
    reg = EntityRegistry(book_id="test_alias_reg")
    id_john = reg.register_character("John Straker", "Trainer", ["Straker"], chapter_num=1)
    id_mrs = reg.register_character("Mrs. Straker", "Widow", ["Mrs Straker"], chapter_num=2)

    assert id_john != id_mrs
    assert id_john == "c_john_straker"
    assert id_mrs == "c_mrs_straker"
    assert len(reg.characters) == 2


# ============================================================================
# 5. Idempotent Re-import & Deduplication
# ============================================================================

def test_idempotent_reimport():
    """Verify that re-running extraction on identical chapters generates deterministic IDs without duplicates."""
    chapters = [{
        "chapter_number": 1,
        "title": "Chapter 1",
        "content": "Mr. Sherlock Holmes sat with Dr. Watson. Inspector Gregory arrived shortly after.",
    }]

    # Run extraction with deterministic fallback
    with patch("app.llm.extractor.get_llm_client", return_value=(None, None)):
        res1 = run_story_extraction_pipeline("Story", "Author", "", chapters, "idempotent_test")
        res2 = run_story_extraction_pipeline("Story", "Author", "", chapters, "idempotent_test")

    char_ids_1 = sorted([c.id for c in res1.dataset.characters])
    char_ids_2 = sorted([c.id for c in res2.dataset.characters])
    assert char_ids_1 == char_ids_2
    assert len(res1.dataset.characters) == len(res2.dataset.characters)


# ============================================================================
# 6. Safe Fallback Behavior when LLM is Unavailable
# ============================================================================

def test_missing_llm_fallback_creates_no_fabricated_claims():
    """Verify that when no LLM is available, extraction falls back safely with NO dummy claims."""
    chapters = [
        {
            "chapter_number": 1,
            "title": "Chapter 1",
            "content": "Lord Harrington walked into Blackwood Manor. The storm raged outside.",
        }
    ]

    with patch("app.llm.extractor.get_llm_client", return_value=(None, None)):
        res = run_story_extraction_pipeline("Story", "Author", "", chapters, "test_no_llm")

    assert res.status == "basic_extraction"
    assert "Basic extraction only" in res.status_message
    assert "Configure an LLM API key" in res.status_message

    # Must NOT have fabricated dummy claims (no PRESENT_AT connecting first char to first loc)
    for cl in res.dataset.claims:
        assert cl.text != "Lord Harrington is situated at Blackwood Manor."
        assert cl.validation != "alleged" or cl.kind != "PRESENT_AT"


# ============================================================================
# 7. FalkorDB Mapping and Explorer Compatibility
# ============================================================================

@requires_falkordb
def test_falkordb_mapping_and_explorer_compatibility():
    """Verify that extracted dataset seeds cleanly into FalkorDB and visible_graph reads nodes/edges."""
    chapters = [{
        "chapter_number": 1,
        "title": "Chapter 1",
        "content": "Colonel Ross was the owner of Silver Blaze. Inspector Gregory investigated the disappearance.",
    }]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """
    {
      "characters": [
        {"name": "Colonel Ross", "role": "Horse Owner", "aliases": ["Ross"]},
        {"name": "Silver Blaze", "role": "Racehorse", "aliases": []}
      ],
      "locations": [
        {"name": "Dartmoor", "context": "Moorland region"}
      ],
      "factions": [],
      "events": [
        {
          "title": "The Disappearance",
          "occurrence_chapter": 1,
          "reveal_chapter": 1,
          "participants": [{"character_name": "Silver Blaze", "role": "missing"}]
        }
      ],
      "claims": [
        {
          "subject_name": "Colonel Ross",
          "predicate": "OWNS",
          "object_name": "Silver Blaze",
          "role": "owner",
          "text": "Colonel Ross is the owner of Silver Blaze.",
          "validation": "confirmed",
          "reveal_chapter": 1,
          "excerpt": "Colonel Ross was the owner of Silver Blaze"
        }
      ]
    }
    """

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("app.llm.extractor.get_llm_client", return_value=(mock_client, "mock-model")):
        res = run_story_extraction_pipeline(
            title="Seeding Test",
            author="Author",
            description="",
            chapters_data=chapters,
            book_id="test_seeding_compat",
        )

    # Seed into FalkorDB under isolated graph name
    graph_name = "story_test_seeding_compat"
    seed_story_to_falkordb(res.dataset, graph_name=graph_name)

    # Verify visible_graph can read it
    token = current_graph_name.set(graph_name)
    try:
        graph_data = visible_graph(chapter=1)
        nodes = graph_data["nodes"]
        edges = graph_data["edges"]

        assert len(nodes) >= 2
        node_labels = [n["data"]["label"] for n in nodes]
        assert "Colonel Ross" in node_labels
        assert "Silver Blaze" in node_labels

        assert len(edges) >= 1
        assert any(e["data"]["label"] == "OWNS" for e in edges)

        # Test node details
        ross_details = get_node_details("c_colonel_ross", chapter=1)
        assert ross_details is not None
        assert ross_details["node"]["name"] == "Colonel Ross"
    finally:
        current_graph_name.reset(token)


# ============================================================================
# 8. Story Isolation: No Story-Specific Vocabulary Leaks to Unrelated Books
# ============================================================================

def test_independent_story_isolation_no_leakage():
    """Verify extracting an independent story (Poe's The Tell-Tale Heart) produces ZERO Silver Blaze/Glass Orchard artifacts."""
    poe_chapter = [{
        "chapter_number": 1,
        "title": "The Old Man's Eye",
        "content": (
            "The old man was lying quietly in his bed. "
            "Three police officers arrived at four in the morning to investigate the neighbors' complaints. "
            "The narrator smiled cordially and invited the officers into the chamber."
        ),
    }]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = """
    {
      "characters": [
        {"name": "The Old Man", "role": "Victim", "aliases": ["Old Man"]},
        {"name": "The Narrator", "role": "Protagonist / Murderer", "aliases": []},
        {"name": "The Police Officers", "role": "Investigating Officers", "aliases": ["Officers"]}
      ],
      "locations": [
        {"name": "The Chamber", "context": "The old man's bedroom"}
      ],
      "factions": [],
      "events": [
        {
          "title": "Police Visit to the Chamber",
          "occurrence_chapter": 1,
          "reveal_chapter": 1,
          "participants": [
            {"character_name": "The Narrator", "role": "host"},
            {"character_name": "The Police Officers", "role": "investigator"}
          ]
        }
      ],
      "claims": [
        {
          "subject_name": "The Police Officers",
          "predicate": "INVESTIGATES",
          "object_name": "The Chamber",
          "role": "investigators",
          "text": "The police officers investigated the chamber.",
          "validation": "confirmed",
          "reveal_chapter": 1,
          "excerpt": "Three police officers arrived at four in the morning to investigate"
        }
      ]
    }
    """

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("app.llm.extractor.get_llm_client", return_value=(mock_client, "mock-model")):
        res = run_story_extraction_pipeline(
            title="The Tell-Tale Heart",
            author="Edgar Allan Poe",
            description="A classic psychological tale.",
            chapters_data=poe_chapter,
            book_id="poe_tell_tale",
        )

    # Verify no leaks of Silver Blaze or Glass Orchard
    all_names = [c.name.lower() for c in res.dataset.characters]
    all_roles = [c.role.lower() for c in res.dataset.characters]
    all_predicates = [cl.kind for cl in res.dataset.claims]

    leaked_words = ["holmes", "straker", "ross", "gregory", "silver blaze", "elias", "mara", "halden"]
    for word in leaked_words:
        assert not any(word in n for n in all_names), f"Leaked word '{word}' found in character names!"
        assert not any(word in r for r in all_roles), f"Leaked word '{word}' found in character roles!"

    # Verify genuine extracted entities
    assert any("old man" in n for n in all_names)
    assert any("police" in n for n in all_names)
