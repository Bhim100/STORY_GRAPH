"""Smoke test verifying FalkorDB connectivity and graph operations."""
import pytest
from app.db import get_falkordb_client, ping


requires_falkordb = pytest.mark.skipif(not ping(), reason="Requires live FalkorDB instance")


@requires_falkordb
def test_falkordb_ping():
    """Verify that FalkorDB responds to ping."""
    assert ping() is True, "FalkorDB ping failed. Check if container is running on configured port."


@requires_falkordb
def test_db_connection():
    """Smoke test: create throwaway graph, create node, query node, assert, and cleanup."""
    client = get_falkordb_client()
    test_graph_name = "test_smoke_graph"
    graph = client.select_graph(test_graph_name)

    try:
        # Create a test node
        graph.query("CREATE (:Test {id: 't1'})")

        # Query the node
        res = graph.query("MATCH (n:Test) RETURN n.id")

        # Assert result is 't1'
        assert len(res.result_set) == 1, f"Expected 1 record, got {len(res.result_set)}"
        assert res.result_set[0][0] == "t1", f"Expected 't1', got {res.result_set[0][0]}"
    finally:
        # Delete throwaway graph
        try:
            graph.delete()
        except Exception:
            pass
