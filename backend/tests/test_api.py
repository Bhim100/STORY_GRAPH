"""Integration tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import ping

client = TestClient(app)
requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


def test_api_root():
    """Verify API root status endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "StoryGraph API"
    assert data["status"] == "online"


def test_api_health():
    """Verify health and database status endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "database_unavailable")
    assert data["database"] == "falkordb"
    assert data["graph"] == "glass_orchard"


@requires_falkordb
def test_api_story_info():
    """Verify story metadata endpoint."""
    response = client.get("/api/story")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "glass_orchard"
    assert "The Glass Orchard" in data["title"]
    assert data["max_chapters"] == 8


@requires_falkordb
def test_api_graph_chapter_boundary():
    """Verify graph data conforms strictly to chapter boundary."""
    # At chapter 1, Ruth Ames should NOT be in the graph nodes
    res_ch1 = client.get("/api/graph?chapter=1")
    assert res_ch1.status_code == 200
    data_ch1 = res_ch1.json()
    node_ids_ch1 = [n["data"]["id"] for n in data_ch1["nodes"]]
    assert "c_elias_thorne" in node_ids_ch1
    assert "c_mara_voss" in node_ids_ch1
    assert "c_ruth_ames" not in node_ids_ch1

    # At chapter 6, Ruth Ames should be visible
    res_ch6 = client.get("/api/graph?chapter=6")
    assert res_ch6.status_code == 200
    data_ch6 = res_ch6.json()
    node_ids_ch6 = [n["data"]["id"] for n in data_ch6["nodes"]]
    assert "c_ruth_ames" in node_ids_ch6


@requires_falkordb
def test_api_entities_resolve():
    """Verify entity resolution endpoint."""
    # Ambiguous query "Thorne"
    res = client.get("/api/entities/resolve?name=Thorne&chapter=1")
    assert res.status_code == 200
    matches = res.json()["matches"]
    match_ids = [m["id"] for m in matches]
    assert "c_elias_thorne" in match_ids
    assert "c_edith_thorne" in match_ids

    # Hidden entity at Ch 5 returns 0 matches
    res_hidden = client.get("/api/entities/resolve?name=Ruth%20Ames&chapter=5")
    assert res_hidden.status_code == 200
    assert len(res_hidden.json()["matches"]) == 0


@requires_falkordb
def test_api_node_details_revealed_and_hidden():
    """Verify node details endpoint returns case notes or 404 if hidden."""
    # Revealed node at Ch 1
    res = client.get("/api/nodes/c_mara_voss?chapter=1")
    assert res.status_code == 200
    data = res.json()
    assert data["node"]["id"] == "c_mara_voss"
    assert data["node"]["name"] == "Mara Voss"
    assert len(data["connections"]) >= 1
    assert len(data["evidence"]) >= 1

    # Hidden node at Ch 5 returns 404
    res_hidden = client.get("/api/nodes/c_ruth_ames?chapter=5")
    assert res_hidden.status_code == 404

    # Revealed at Ch 6
    res_revealed = client.get("/api/nodes/c_ruth_ames?chapter=6")
    assert res_revealed.status_code == 200
    assert res_revealed.json()["node"]["id"] == "c_ruth_ames"


@requires_falkordb
def test_api_connection():
    """Verify connection lookup between two entities."""
    res = client.get("/api/connection?source=c_mara_voss&target=c_elias_thorne&chapter=1")
    assert res.status_code == 200
    path = res.json()["path"]
    assert path is not None
    assert len(path["nodes"]) == 2
    assert path["relationships"][0]["type"] == "EMPLOYED_BY"


@requires_falkordb
def test_api_ask():
    """Verify /api/ask endpoint executes agent workflow."""
    res = client.post("/api/ask", json={
        "question": "How is Mara Voss connected to Elias Thorne?",
        "chapter": 1
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "answered"
    assert "Mara Voss" in data["answer"]
    assert len(data["relationships"]) == 1
    assert len(data["evidence"]) >= 1


@requires_falkordb
def test_api_ask_entity_profile():
    """Verify /api/ask endpoint handles entity profile queries with evidence and relationships."""
    res = client.post("/api/ask", json={
        "question": "Tell me about Mara Voss",
        "chapter": 1
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "entity_profile"
    assert "Mara Voss" in data["answer"]
    assert "Estate archivist" in data["answer"]
    assert "Employment agreement" in data["answer"]
    assert len(data["nodes"]) >= 1
    assert len(data["relationships"]) >= 1
    assert len(data["evidence"]) >= 1


@requires_falkordb
def test_api_ask_collection_household():
    """Verify /api/ask endpoint handles collection queries with members and evidence."""
    res = client.post("/api/ask", json={
        "question": "Who is in the Thorne household?",
        "chapter": 1
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "collection_query"
    assert "Jonas Reed" in data["answer"]
    assert len(data["members"]) == 1
    assert data["members"][0]["name"] == "Jonas Reed"
    assert len(data["relationships"]) == 1
    assert len(data["evidence"]) >= 1
    assert "Unverified membership claims exist" in data["answer"]



@requires_falkordb
def test_api_ask_manor_distinction():
    """Verify /api/ask endpoint distinguishes manor location from household membership."""
    res = client.post("/api/ask", json={
        "question": "Who lives at Thorne Manor?",
        "chapter": 1
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "collection_query"
    assert "does not establish supported residence or employment relationships" in data["answer"]
    assert len(data["nodes"]) == 0
    assert len(data["members"]) == 0


def test_api_validation_error():
    """Verify parameter validation handles invalid chapter appropriately."""
    res = client.get("/api/graph?chapter=0")
    assert res.status_code == 422

