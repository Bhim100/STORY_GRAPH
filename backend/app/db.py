from contextvars import ContextVar
from typing import Optional
from falkordb import FalkorDB
from app.config import (
    FALKORDB_HOST,
    FALKORDB_PORT,
    FALKORDB_PASSWORD,
    FALKORDB_USERNAME,
    GRAPH_NAME,
)

# ContextVar allowing per-request graph isolation across books
current_graph_name: ContextVar[str] = ContextVar("current_graph_name", default=GRAPH_NAME)

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
    """Selects and returns a graph instance by name, falling back to request-scoped current_graph_name."""
    client = get_falkordb_client()
    target_graph = graph_name or current_graph_name.get() or GRAPH_NAME
    return client.select_graph(target_graph)



def ping() -> bool:
    """Verifies that FalkorDB is reachable and responding."""
    try:
        client = get_falkordb_client()
        # Connection check via redis ping on the underlying client
        return bool(client.connection.ping())
    except Exception:
        return False
