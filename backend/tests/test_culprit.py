"""Unit and integration tests for deterministic culprit reasoning over supported graph claims and evidence."""
import pytest
from starlette.testclient import TestClient

from app.db import ping
from app.llm.agent import answer_question
from app.llm.router import QuestionType
from app.main import app

client = TestClient(app)
requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


@requires_falkordb
def test_culprit_early_chapter_1():
    """Verify 'Who killed Elias Thorne?' at Chapter 1.
    
    Requirements:
    - Must NOT name Halden as the killer.
    - Status must be 'no established culprit yet'.
    - Must label Jonas's dispute as an unproven allegation, not a confirmed murder.
    - Death event must be reported as not yet revealed.
    """
    res = answer_question("Who killed Elias Thorne?", chapter=1)
    assert res["status"] == "culprit_query"
    assert res["culprit_status"] == "no_established_culprit"
    assert res["culprit"] is None
    assert res["path"] is None

    ans = res["answer"]
    assert "Status: no established culprit yet" in ans
    assert "not yet occurred or been discovered" in ans
    assert "Dr. Pavel Halden" in ans
    # Crucial: Halden must NOT be named as the killer
    assert "halden killed" not in ans.lower()
    assert "halden is the killer" not in ans.lower()
    assert "halden is the culprit" not in ans.lower()

    # Jonas is labeled as an allegation, not a confirmed killer
    assert "[Allegation]" in ans
    assert "not constitute a homicide or establish a culprit" in ans or "not a confirmed crime" in ans.lower()
    assert any(e["evidence_id"] == "evi_witness_edith" for e in res["evidence"])


@requires_falkordb
def test_culprit_early_chapter_4():
    """Verify 'Who killed Elias Thorne?' at Chapter 4.
    
    Requirements:
    - Elias is found dead in greenhouse (revealed Ch. 2).
    - Cause of death remains completely unknown.
    - Must NOT name Halden as the killer.
    - Status must be 'no established culprit yet'.
    """
    res = answer_question("Who killed Elias Thorne?", chapter=4)
    assert res["status"] == "culprit_query"
    assert res["culprit_status"] == "no_established_culprit"
    assert res["culprit"] is None
    assert res["path"] is None

    ans = res["answer"]
    assert "Status: no established culprit yet" in ans
    assert "Elias Thorne is found dead in the greenhouse" in ans
    assert "cause of death remains completely unknown" in ans or "no lethal weapon, poison, or mechanism" in ans.lower()
    # Crucial: Halden must NOT be named as the killer
    assert "halden killed" not in ans.lower()
    assert "halden is the killer" not in ans.lower()
    assert "halden is the culprit" not in ans.lower()
    assert "vial" not in ans.lower()
    assert "tampered" not in ans.lower()


@requires_falkordb
def test_culprit_intermediate_chapter_5():
    """Verify 'Who killed Elias Thorne?' at Chapter 5.
    
    Requirements:
    - Status must be 'suspect or allegation'.
    - Poisoned cider is confirmed cause of death (backed by toxicology evidence from Ch. 5).
    - Mara's suspicion of Halden based on ledger is reported.
    - Must NOT call Halden the confirmed culprit.
    - Must report the data gap: identity of who tampered with the cider is unestablished.
    """
    res = answer_question("Who killed Elias Thorne?", chapter=5)
    assert res["status"] == "culprit_query"
    assert res["culprit_status"] == "suspect_or_allegation"
    assert res["culprit"] is None
    assert res["path"] is None

    ans = res["answer"]
    assert "Status: suspect or allegation" in ans
    assert "[Confirmed] Elias Thorne was killed by poisoned cider" in ans
    assert "Residue in the glass decanter matches the lethal agent" in ans
    assert "Mara suspects Halden" in ans
    assert "Totals on pages 12 and 14 disagree" in ans

    # Must NOT call Halden the confirmed culprit
    assert "he is NOT the confirmed culprit" in ans or "not the confirmed culprit" in ans.lower()
    assert "Data Gap: The identity of who introduced poison into the cider is not established" in ans or "not established at Chapter 5" in ans
    assert "Evidence Grounding" in ans
    assert "without naming Halden" in ans or "does not name Dr. Pavel Halden" in ans

    # Verify structured evidence includes toxicology and ledger page
    evidence_ids = [e["evidence_id"] for e in res["evidence"]]
    assert "evi_toxicology" in evidence_ids
    assert "evi_ledger_page" in evidence_ids
    assert "evi_vial" not in evidence_ids  # Ch 7 only

    # Verify returned nodes and relationships connect properly
    assert len(res["nodes"]) == 2
    assert len(res["relationships"]) == 1
    assert res["relationships"][0]["source"] == res["nodes"][0]["id"] == "ev_cider_tampered"
    assert res["relationships"][0]["target"] == res["nodes"][1]["id"] == "ev_elias_death"


@requires_falkordb
def test_culprit_final_chapter_7():
    """Verify 'Who killed Elias Thorne?' at Chapter 7.
    
    Requirements:
    - Status must be 'culprit established by visible supported claims/evidence'.
    - Identifies Dr. Pavel Halden as the culprit.
    - Reasoning chain shows:
      1. Motive / trigger (Ch. 7, evi_vial, with evidence grounding note)
      2. Act of tampering (Ch. 7, cl_halden_perp, evi_vial, with evidence grounding note)
      3. Lethal causation (Ch. 5, cl_causal_tampered_death, evi_toxicology)
      4. Deductive inference labeled
      5. Graph modeling note explaining lack of direct edge from death event to Elias character
    - Returns structurally complete graph path where every edge connects adjacent nodes:
      len(nodes) == len(relationships) + 1 == 3
      Halden -> Cider Tampering -> Elias's Death
    """
    res = answer_question("Who killed Elias Thorne?", chapter=7)
    assert res["status"] == "culprit_query"
    assert res["culprit_status"] == "culprit_established"
    assert res["culprit"] is not None
    assert res["culprit"]["id"] == "c_pavel_halden"
    assert res["culprit"]["name"] == "Dr. Pavel Halden"

    # Verify path structure: strictly complete graph path with no dangling nodes
    path = res["path"]
    assert path is not None
    assert len(path["nodes"]) == 3
    assert len(path["relationships"]) == 2
    assert len(path["nodes"]) == len(path["relationships"]) + 1

    node_ids = [n["id"] for n in path["nodes"]]
    assert node_ids == ["c_pavel_halden", "ev_cider_tampered", "ev_elias_death"]
    assert "c_elias_thorne" not in node_ids  # Elias is not an unconnected dangling node

    # Verify every edge connects adjacent nodes
    for i, rel in enumerate(path["relationships"]):
        assert rel["source"] == path["nodes"][i]["id"]
        assert rel["target"] == path["nodes"][i + 1]["id"]

    assert path["relationships"][0]["type"] == "PARTICIPATED_IN"
    assert path["relationships"][0]["role"] == "perpetrator"
    assert path["relationships"][1]["type"] == "CAUSED"

    # Top-level nodes and relationships match path
    assert len(res["nodes"]) == 3
    assert len(res["relationships"]) == 2
    assert [n["id"] for n in res["nodes"]] == node_ids

    # Evidence attachment
    evi_ids = [e["evidence_id"] for e in res["evidence"]]
    assert "evi_vial" in evi_ids
    assert "evi_toxicology" in evi_ids

    ans = res["answer"]
    assert "Status: culprit established by visible supported claims/evidence" in ans
    assert "Dr. Pavel Halden tampered with the cider as perpetrator" in ans or "perpetrator" in ans.lower()
    assert "The poisoned cider directly caused Elias Thorne's death" in ans
    assert "Deductive Inference" in ans
    assert "Graph Modeling Note" in ans
    assert "Dr. Pavel Halden is established as the culprit" in ans

    # Evidence grounding distinctions
    assert "physical possession" in ans.lower()
    assert "deductive conclusion" in ans.lower()
    assert "without an unmediated character edge" in ans


@requires_falkordb
def test_culprit_path_adjacency_and_evidence_grounding_rigor():
    """Verify that every returned path edge exists in FalkorDB and connects adjacent nodes,
    and that cited excerpts actually support their specific claim rather than over-claiming.
    """
    from app.db import get_graph
    graph = get_graph("glass_orchard")

    res = answer_question("Who killed Elias Thorne?", chapter=7)
    path = res["path"]
    assert path is not None

    # 1. Structural Adjacency Check
    nodes = path["nodes"]
    relationships = path["relationships"]
    assert len(nodes) == len(relationships) + 1

    for i, rel in enumerate(relationships):
        # Assert adjacent connectivity
        assert rel["source"] == nodes[i]["id"]
        assert rel["target"] == nodes[i + 1]["id"]

        # Assert edge actually exists in FalkorDB
        db_check = graph.query(
            "MATCH (a {id: $src})-[r]->(b {id: $tgt}) WHERE type(r) = $rel_type RETURN count(r)",
            {"src": rel["source"], "tgt": rel["target"], "rel_type": rel["type"]}
        )
        assert db_check.result_set[0][0] >= 1

    # 2. Excerpt grounding check: Verify that evi_ledger_page text does not contain Halden
    evi_ledger = next((e for e in res.get("evidence", []) if e.get("evidence_id") == "evi_ledger_page"), None)
    res_ch5 = answer_question("Who killed Elias Thorne?", chapter=5)
    ledger_evi_ch5 = next(e for e in res_ch5["evidence"] if e["evidence_id"] == "evi_ledger_page")
    assert "4,200" in ledger_evi_ch5["excerpt"]
    assert "halden" not in ledger_evi_ch5["excerpt"].lower()

    # 3. Excerpt grounding check: Verify that evi_vial text only mentions finding toxic compound in bag
    vial_evi = next(e for e in res["evidence"] if e["evidence_id"] == "evi_vial")
    assert "medical bag" in vial_evi["excerpt"]
    assert "tamper" not in vial_evi["excerpt"].lower()
    assert "motive" not in vial_evi["excerpt"].lower()


@requires_falkordb
def test_culprit_false_lead_handling():
    """Verify contradictory and false-lead claims (e.g. quarrel causing death, Jonas dispute) are not treated as culprit."""
    # At Chapter 2, quarrel is cataloged as a false lead
    res_ch2 = answer_question("Who killed Elias Thorne?", chapter=2)
    assert res_ch2["culprit_status"] == "no_established_culprit"
    assert res_ch2["culprit"] is None
    assert "[False Lead]" in res_ch2["answer"]
    assert "Jonas" not in [n["name"] for n in [res_ch2.get("culprit")] if n]

    # At Chapter 6, Jonas is cleared as ally
    res_ch6 = answer_question("Who killed Elias Thorne?", chapter=6)
    assert res_ch6["culprit_status"] == "suspect_or_allegation"
    assert "Cleared Suspect" in res_ch6["answer"] or "cleared of early suspicion" in res_ch6["answer"]


@requires_falkordb
def test_culprit_api_endpoint_integration():
    """Integration test: Verify /api/ask HTTP endpoint returns structured culprit_query payload."""
    res = client.post("/api/ask", json={
        "question": "Who killed Elias Thorne?",
        "chapter": 7,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "culprit_query"
    assert data["culprit_status"] == "culprit_established"
    assert data["culprit"]["name"] == "Dr. Pavel Halden"
    assert data["path"] is not None
    assert len(data["path"]["nodes"]) == 3
    assert len(data["path"]["relationships"]) == 2
    assert len(data["evidence"]) >= 2
