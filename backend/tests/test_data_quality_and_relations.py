"""Tests for StoryGraph data quality, canonical entity resolution, specific relationships, and Cytoscape invariants."""
import pytest
from typing import Dict, Any, List
from app.models import StoryDataset, Character, Location, Event, Claim, Evidence
from app.importer import extract_candidate_dataset_from_text
from app.graph.explorer import find_connection, get_node_details, visible_graph
from app.graph.seed import seed_story_to_falkordb


def sample_silver_blaze_chapters() -> List[Dict[str, Any]]:
    """Synthetic multi-chapter sample with controlled provenance and chapter boundaries."""
    return [
        {
            "chapter_number": 1,
            "title": "Chapter 1",
            "content": (
                "The disappearance of Silver Blaze and the murder of John Straker shocked all of England. "
                "On Tuesday evening I received telegrams from both Colonel Ross, the owner of the horse, "
                "and from Inspector Gregory, who is looking after the case, inviting my co-operation. "
                "The trainer, John Straker, is a retired jockey who rode in Colonel Ross's colours before he became too heavy. "
                "He has been in your service some years, Colonel Ross? I have always found him an excellent servant, replied the Colonel. "
                "Silver Blaze is the pride of Dartmoor. "
                "Mr. Holmes sat down to breakfast with Dr. Watson. "
                "Inspector Gregory investigated the mystery. "
                "Holmes and Watson discussed the curious incident of the dog in the night-time."
            ),
        },
        {
            "chapter_number": 2,
            "title": "Chapter 2",
            "content": (
                "Inspector Gregory has arrested Fitzroy Simpson as the chief suspect. "
                "Mrs. Straker, the widow of the murdered trainer, was weeping in her parlor. "
                "Mr. John Straker was discovered early that morning. "
                "Silas Brown, who was the manager of the Capland stables, spoke to Mr. Holmes. "
                "Mr. Silas Brown replied with indignation. "
                "Colonel Ross glanced at his watch with impatience."
            ),
        },
        {
            "chapter_number": 3,
            "title": "Chapter 3",
            "content": (
                "At the Mapleton stables, Mr. Brown admitted that Silver Blaze had been in his care. "
                "Sherlock Holmes confronted Silas Brown directly. "
                "The Wessex Cup race approached as the mystery unfolded."
            ),
        },
    ]


def test_1_entity_aliases_resolve_to_one_canonical_entity():
    """1. Entity aliases resolve to one canonical entity."""
    chapters = sample_silver_blaze_chapters()
    dataset = extract_candidate_dataset_from_text(
        title="Silver Blaze",
        author="Arthur Conan Doyle",
        description="A Sherlock Holmes adventure",
        chapters_data=chapters,
        book_id="test_silver_blaze"
    )

    chars_by_id = {c.id: c for c in dataset.characters}

    # Holmes check: Sherlock Holmes and Mr. Holmes must resolve to a single canonical entity
    assert "c_sherlock_holmes" in chars_by_id
    holmes = chars_by_id["c_sherlock_holmes"]
    assert holmes.name == "Sherlock Holmes"
    assert any("holmes" in a.lower() for a in holmes.aliases)
    assert "c_mr_holmes" not in chars_by_id

    # Straker check: John Straker and Mr. John Straker must resolve to one canonical entity
    assert "c_john_straker" in chars_by_id
    straker = chars_by_id["c_john_straker"]
    assert straker.name == "John Straker"
    assert "c_mr_john_straker" not in chars_by_id

    # Silas Brown check: Silas Brown, Mr. Silas Brown, and Mr. Brown must resolve to c_silas_brown
    assert "c_silas_brown" in chars_by_id
    silas = chars_by_id["c_silas_brown"]
    assert silas.name == "Silas Brown"
    assert "c_mr_silas_brown" not in chars_by_id
    assert "c_mr_brown" not in chars_by_id

    # Colonel Ross check: single canonical node
    assert "c_colonel_ross" in chars_by_id
    assert "c_inspector_gregory" in chars_by_id
    assert "c_silver_blaze" in chars_by_id


def test_2_repeated_passages_do_not_create_duplicate_edges_or_evidence():
    """2. Repeated passages do not create duplicate edges or evidence."""
    # Create chapters with duplicate repeated sentences
    repeated_chapters = [
        {
            "chapter_number": 1,
            "title": "Chapter 1",
            "content": (
                "Colonel Ross, the owner of the horse, arrived at King's Pyland. "
                "Colonel Ross, the owner of the horse, arrived at King's Pyland. "
                "Colonel Ross is the fortunate owner of Silver Blaze."
            ),
        },
        {
            "chapter_number": 2,
            "title": "Chapter 2",
            "content": (
                "Colonel Ross, the owner of the horse, spoke to the inspector. "
                "Colonel Ross owns the horse Silver Blaze."
            ),
        },
    ]

    dataset = extract_candidate_dataset_from_text(
        title="Deduplication Test",
        author="Arthur Conan Doyle",
        description="Testing deduplication",
        chapters_data=repeated_chapters,
        book_id="test_dedup"
    )

    # Count how many OWNS claims exist between Colonel Ross and Silver Blaze
    owns_claims = [
        cl for cl in dataset.claims
        if cl.subject == "c_colonel_ross" and cl.object == "c_silver_blaze" and cl.kind == "OWNS"
    ]
    assert len(owns_claims) == 1, f"Expected exactly 1 OWNS claim, found {len(owns_claims)}"

    # Check evidence linked to that claim is not infinitely duplicated
    claim_id = owns_claims[0].id
    linked_evidence = [ev for ev in dataset.evidence if claim_id in ev.supports]
    assert 1 <= len(linked_evidence) <= 3, f"Evidence count should be between 1 and 3, got {len(linked_evidence)}"


def test_3_relationships_receive_specific_type_only_when_supported():
    """3. A relationship receives a specific type only when its passage supports that type."""
    chapters = sample_silver_blaze_chapters()
    dataset = extract_candidate_dataset_from_text(
        title="Silver Blaze Vocabulary",
        author="Arthur Conan Doyle",
        description="Controlled relationships",
        chapters_data=chapters,
        book_id="test_vocab"
    )

    claims_by_kind = {}
    for cl in dataset.claims:
        claims_by_kind.setdefault(cl.kind, []).append(cl)

    # OWNS: Colonel Ross owns Silver Blaze
    assert "OWNS" in claims_by_kind
    owns = [cl for cl in claims_by_kind["OWNS"] if cl.subject == "c_colonel_ross" and cl.object == "c_silver_blaze"]
    assert len(owns) == 1
    assert owns[0].validation == "confirmed"

    # TRAINER_OF: John Straker is trainer of Silver Blaze
    assert "TRAINER_OF" in claims_by_kind
    trainer = [cl for cl in claims_by_kind["TRAINER_OF"] if cl.subject == "c_john_straker" and cl.object == "c_silver_blaze"]
    assert len(trainer) == 1
    assert trainer[0].validation == "confirmed"

    # EMPLOYS: Colonel Ross employs John Straker
    assert "EMPLOYS" in claims_by_kind
    employs = [cl for cl in claims_by_kind["EMPLOYS"] if cl.subject == "c_colonel_ross" and cl.object == "c_john_straker"]
    assert len(employs) == 1
    assert employs[0].validation == "confirmed"

    # INVESTIGATES: Inspector Gregory investigates the case/event
    assert "INVESTIGATES" in claims_by_kind
    gregory_inv = [cl for cl in claims_by_kind["INVESTIGATES"] if cl.subject == "c_inspector_gregory"]
    assert len(gregory_inv) >= 1
    assert gregory_inv[0].validation == "confirmed"


def test_4_unsupported_co_occurrence_not_confirmed():
    """4. Unsupported/co-occurrence-only relationships are not marked confirmed."""
    chapters = [
        {
            "chapter_number": 1,
            "title": "Chapter 1",
            "content": (
                "Inspector Gregory has arrested Fitzroy Simpson as a suspect in the crime. "
                "Sherlock Holmes and Dr. Watson had a conversation together in their rooms."
            ),
        }
    ]

    dataset = extract_candidate_dataset_from_text(
        title="Validation Test",
        author="Arthur Conan Doyle",
        description="Testing validation tags",
        chapters_data=chapters,
        book_id="test_validation"
    )

    for cl in dataset.claims:
        if cl.kind == "SUSPECTS":
            # Suspect claims must be marked alleged
            assert cl.validation == "alleged", f"SUSPECTS claim should be alleged, got {cl.validation}"
        elif cl.kind == "INTERACTED_WITH":
            # Conversational interaction without proof of formal deed must be alleged
            assert cl.validation == "alleged", f"INTERACTED_WITH claim should be alleged, got {cl.validation}"


def test_5_path_edges_connect_adjacent_nodes():
    """5. Each returned path edge connects its adjacent nodes."""
    story = StoryDataset(
        story_id="test_path_connectivity",
        title="Path Connectivity Test",
        description="Verifies path edge connectivity invariant",
        characters=[
            Character(id="c_alice", story_id="test_path_connectivity", name="Alice", aliases=[], role="Detective", reveal_chapter=1),
            Character(id="c_bob", story_id="test_path_connectivity", name="Bob", aliases=[], role="Assistant", reveal_chapter=1),
            Character(id="c_carol", story_id="test_path_connectivity", name="Carol", aliases=[], role="Witness", reveal_chapter=1),
        ],
        locations=[],
        factions=[],
        events=[],
        claims=[
            Claim(
                id="cl_ab",
                story_id="test_path_connectivity",
                kind="INTERACTED_WITH",
                subject="c_alice",
                object="c_bob",
                text="Alice spoke with Bob.",
                reveal_chapter=1,
                validation="confirmed"
            ),
            Claim(
                id="cl_bc",
                story_id="test_path_connectivity",
                kind="INTERACTED_WITH",
                subject="c_bob",
                object="c_carol",
                text="Bob interviewed Carol.",
                reveal_chapter=1,
                validation="confirmed"
            ),
        ],
        evidence=[
            Evidence(id="evi_ab", story_id="test_path_connectivity", kind="document", excerpt="Proof Alice spoke with Bob.", source_chapter=1, reveal_chapter=1, supports=["cl_ab"]),
            Evidence(id="evi_bc", story_id="test_path_connectivity", kind="document", excerpt="Proof Bob spoke with Carol.", source_chapter=1, reveal_chapter=1, supports=["cl_bc"]),
        ]
    )

    seed_story_to_falkordb(story, graph_name="test_path_connectivity")
    from app.db import current_graph_name
    token = current_graph_name.set("test_path_connectivity")
    try:
        path = find_connection("c_alice", "c_carol", chapter=1)
        assert path is not None, "Path between Alice and Carol must be found"
        nodes = path["nodes"]
        edges = path["edges"]

        assert len(nodes) == 3
        assert len(edges) == 2

        # Invariant: Each returned path edge connects its adjacent nodes
        for i in range(len(edges)):
            edge = edges[i]
            expected_nodes = {nodes[i]["id"], nodes[i + 1]["id"]}
            actual_nodes = {edge["source"], edge["target"]}
            assert actual_nodes == expected_nodes, (
                f"Edge {i} {actual_nodes} does not connect adjacent nodes {expected_nodes}"
            )
    finally:
        current_graph_name.reset(token)


def test_6_chapter_filtering_hides_later_evidence_and_relationships():
    """6. Chapter filtering still hides later evidence and relationships."""
    story = StoryDataset(
        story_id="test_spoiler_filtering",
        title="Spoiler Filtering Test",
        description="Verifies spoiler boundaries on graph and node queries",
        characters=[
            Character(id="c_investigator", story_id="test_spoiler_filtering", name="Investigator", aliases=[], role="Detective", reveal_chapter=1),
            Character(id="c_owner", story_id="test_spoiler_filtering", name="Owner", aliases=[], role="Victim", reveal_chapter=1),
            Character(id="c_secret_accomplice", story_id="test_spoiler_filtering", name="Accomplice", aliases=[], role="Accomplice", reveal_chapter=3),
        ],
        locations=[],
        factions=[],
        events=[],
        claims=[
            Claim(
                id="cl_early",
                story_id="test_spoiler_filtering",
                kind="INTERACTED_WITH",
                subject="c_investigator",
                object="c_owner",
                text="Investigator met the Owner in Chapter 1.",
                reveal_chapter=1,
                validation="confirmed"
            ),
            Claim(
                id="cl_late",
                story_id="test_spoiler_filtering",
                kind="EMPLOYS",
                subject="c_owner",
                object="c_secret_accomplice",
                text="Owner secretly employed the accomplice.",
                reveal_chapter=3,
                validation="confirmed"
            ),
        ],
        evidence=[
            Evidence(id="evi_early", story_id="test_spoiler_filtering", kind="document", excerpt="Early evidence excerpt.", source_chapter=1, reveal_chapter=1, supports=["cl_early"]),
            Evidence(id="evi_late", story_id="test_spoiler_filtering", kind="document", excerpt="Late secret ledger discovered in Chapter 3.", source_chapter=3, reveal_chapter=3, supports=["cl_late"]),
        ]
    )

    seed_story_to_falkordb(story, graph_name="test_spoiler_filtering")
    from app.db import current_graph_name
    token = current_graph_name.set("test_spoiler_filtering")
    try:
        # At Chapter 1: Late accomplice, claim, and evidence must be completely hidden
        g1 = visible_graph(chapter=1)
        visible_node_ids = {n["data"]["id"] for n in g1["nodes"]}
        visible_edge_claims = {e["data"]["claim_id"] for e in g1["edges"]}

        assert "c_investigator" in visible_node_ids
        assert "c_owner" in visible_node_ids
        assert "c_secret_accomplice" not in visible_node_ids
        assert "cl_early" in visible_edge_claims
        assert "cl_late" not in visible_edge_claims

        # At Chapter 1: get_node_details on Owner must not reveal Chapter 3 relationships or evidence
        owner_details_ch1 = get_node_details("c_owner", chapter=1)
        assert owner_details_ch1 is not None
        ch1_claim_ids = {c["claim_id"] for c in owner_details_ch1["connections"]}
        ch1_evi_ids = {e["evidence_id"] for e in owner_details_ch1["evidence"]}
        assert "cl_early" in ch1_claim_ids
        assert "cl_late" not in ch1_claim_ids
        assert "evi_early" in ch1_evi_ids
        assert "evi_late" not in ch1_evi_ids

        # At Chapter 3: Late relationship and evidence are revealed
        g3 = visible_graph(chapter=3)
        g3_node_ids = {n["data"]["id"] for n in g3["nodes"]}
        g3_edge_claims = {e["data"]["claim_id"] for e in g3["edges"]}
        assert "c_secret_accomplice" in g3_node_ids
        assert "cl_late" in g3_edge_claims

        owner_details_ch3 = get_node_details("c_owner", chapter=3)
        ch3_claim_ids = {c["claim_id"] for c in owner_details_ch3["connections"]}
        ch3_evi_ids = {e["evidence_id"] for e in owner_details_ch3["evidence"]}
        assert "cl_late" in ch3_claim_ids
        assert "evi_late" in ch3_evi_ids
    finally:
        current_graph_name.reset(token)
