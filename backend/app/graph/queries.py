"""Controlled Cypher query functions for StoryGraph."""
from typing import List, Dict, Any, Optional
from app.db import get_graph


def execute_cypher(query: str, params: Optional[Dict[str, Any]] = None, graph_name: Optional[str] = None):
    """Executes a Cypher query against FalkorDB with parameters."""
    graph = get_graph(graph_name)
    return graph.query(query, params or {})
