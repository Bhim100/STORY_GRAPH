"""FalkorDB database client and connection management."""
from typing import Optional
from falkordb import FalkorDB
from app.config import (
    FALKORDB_HOST,
    FALKORDB_PORT,
    FALKORDB_PASSWORD,
    FALKORDB_USERNAME,
    GRAPH_NAME,
)

_client: Optional[FalkorDB] = None


def get_falkordb_client() -> FalkorDB:
    """Returns or initializes a singleton FalkorDB client."""
    global _client
    if _client is None:
        _client = FalkorDB(
            host=FALKORDB_HOST,
            port=FALKORDB_PORT,
            password=FALKORDB_PASSWORD,
            username=FALKORDB_USERNAME,
        )
    return _client


def get_graph(graph_name: Optional[str] = None):
    """Selects and returns a graph instance by name."""
    client = get_falkordb_client()
    target_graph = graph_name or GRAPH_NAME
    return client.select_graph(target_graph)


def ping() -> bool:
    """Verifies that FalkorDB is reachable and responding."""
    try:
        client = get_falkordb_client()
        # Connection check via redis ping on the underlying client
        return bool(client.connection.ping())
    except Exception:
        return False
