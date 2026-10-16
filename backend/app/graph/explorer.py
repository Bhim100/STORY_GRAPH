"""Spoiler-safe entity resolution, path search, and graph exploration queries."""
from typing import Any, Dict, List, Optional
from app.graph.queries import execute_cypher


def _rows(query: str, params: Optional[Dict[str, Any]] = None) -> List[List[Any]]:
    return execute_cypher(query, params or {}).result_set


def resolve_entity(name: str, chapter: int) -> List[Dict[str, Any]]:
    """Resolves an entity name or alias against visible entities in FalkorDB (reveal_chapter <= chapter)."""
    cleaned_name = name.strip()
    if not cleaned_name:
        return []

    query = """
    MATCH (n)
    WHERE (n:Character OR n:Event OR n:Location OR n:Faction)
      AND n.reveal_chapter <= $chapter
      AND (
        toLower(coalesce(n.name, '')) = toLower($name)
        OR toLower(coalesce(n.title, '')) = toLower($name)
        OR any(alias IN coalesce(n.aliases, []) WHERE toLower(alias) = toLower($name))
      )
    RETURN n.id, coalesce(n.name, n.title), labels(n), n.reveal_chapter
    LIMIT 6
    """
    rows = _rows(query, {"name": cleaned_name, "chapter": chapter})
    return [
        {"id": r[0], "name": r[1], "labels": r[2], "reveal_chapter": r[3]}
        for r in rows
    ]


def get_visible_entities(chapter: int) -> List[Dict[str, Any]]:
    """Returns all entities visible at the specified chapter boundary."""
    query = """
    MATCH (n)
    WHERE (n:Character OR n:Event OR n:Location OR n:Faction)
      AND n.reveal_chapter <= $chapter
    RETURN n.id, coalesce(n.name, n.title), labels(n), coalesce(n.aliases, []), n.reveal_chapter
    ORDER BY n.reveal_chapter ASC
    """
    rows = _rows(query, {"chapter": chapter})
    return [
        {
            "id": r[0],
            "name": r[1],
            "labels": r[2],
            "aliases": r[3],
            "reveal_chapter": r[4],
        }
        for r in rows
    ]


def get_active_claim_ids(chapter: int) -> List[str]:
    """Retrieves all confirmed, evidence-backed claims visible at chapter N that are not superseded."""
    # 1. Claims with visible supporting evidence and validation not debunked
    q_valid = """
    MATCH (evi:Evidence)-[:SUPPORTS]->(c:Claim)
    WHERE evi.reveal_chapter <= $chapter
      AND c.reveal_chapter <= $chapter
      AND c.validation <> 'debunked'
    RETURN collect(DISTINCT c.id) as valid_claims
    """
    res_valid = _rows(q_valid, {"chapter": chapter})
    valid_claims = res_valid[0][0] if res_valid and res_valid[0] else []

    if not valid_claims:
        return []

    # 2. Check for claims superseded by another claim visible at <= chapter
    q_sup = """
    MATCH (c:Claim)
    WHERE c.reveal_chapter <= $chapter AND c.superseded_by <> ''
    MATCH (rep:Claim {id: c.superseded_by})
    WHERE rep.reveal_chapter <= $chapter
    RETURN collect(c.id) as superseded_claims
    """
    res_sup = _rows(q_sup, {"chapter": chapter})
    superseded_claims = set(res_sup[0][0] if res_sup and res_sup[0] else [])

    return [cid for cid in valid_claims if cid not in superseded_claims]


def find_connection(source_id: str, target_id: str, chapter: int, max_hops: int = 5) -> Optional[Dict[str, Any]]:
    """Finds the shortest spoiler-safe path between two entities in FalkorDB.

    Conditions:
    - Intermediate nodes must have reveal_chapter <= chapter.
    - Edges must have reveal_chapter <= chapter.
    - Edges must map to active, confirmed claims with visible supporting evidence at <= chapter.
    """
    active_claims = get_active_claim_ids(chapter)
    if not active_claims:
        return None

    path_query = """
    MATCH p = (a {id: $source})-[*1..5]-(b {id: $target})
    WHERE all(n IN nodes(p) WHERE coalesce(n.reveal_chapter, 1) <= $chapter)
      AND all(r IN relationships(p) WHERE coalesce(r.reveal_chapter, 1) <= $chapter AND r.claim_id IN $active_claims)
    RETURN p
    ORDER BY length(p) ASC
    LIMIT 1
    """
    rows = _rows(path_query, {"source": source_id, "target": target_id, "chapter": chapter, "active_claims": active_claims})
    if not rows or not rows[0]:
        return None

    path_obj = rows[0][0]

    # Extract nodes
    nodes = []
    node_id_map = {}
    for node in path_obj.nodes():
        node_data = {
            "id": node.properties.get("id"),
            "name": node.properties.get("name") or node.properties.get("title", ""),
            "labels": node.labels,
            "reveal_chapter": node.properties.get("reveal_chapter", 1),
        }
        nodes.append(node_data)
        node_id_map[node.id] = node_data["id"]

    # Extract relationships
    relationships = []
    claim_ids = []
    for edge in path_obj.edges():
        claim_id = edge.properties.get("claim_id")
        claim_ids.append(claim_id)
        relationships.append({
            "type": edge.relation,
            "claim_id": claim_id,
            "reveal_chapter": edge.properties.get("reveal_chapter", 1),
            "role": edge.properties.get("role", ""),
            "source": node_id_map.get(edge.src_node),
            "target": node_id_map.get(edge.dest_node),
        })

    # Retrieve supporting evidence for the traversed claims
    evidence_query = """
    MATCH (e:Evidence)-[:SUPPORTS]->(c:Claim)
    WHERE c.id IN $claim_ids
      AND c.reveal_chapter <= $chapter
      AND e.reveal_chapter <= $chapter
    RETURN c.id, c.text, c.kind, e.id, e.kind, e.excerpt, e.source_chapter, e.reveal_chapter
    """
    evi_rows = _rows(evidence_query, {"claim_ids": claim_ids, "chapter": chapter})
    evidence = [
        {
            "claim_id": r[0],
            "claim": r[1],
            "relationship": r[2],
            "id": r[3],
            "kind": r[4],
            "excerpt": r[5],
            "source_chapter": r[6],
            "reveal_chapter": r[7],
        }
        for r in evi_rows
    ]

    return {
        "nodes": nodes,
        "edges": relationships,
        "relationships": relationships,
        "evidence": evidence,
    }


def visible_graph(chapter: int, limit: int = 120) -> Dict[str, Any]:
    """Returns nodes and edges visible at chapter boundary for interactive graph visualization."""
    active_claims = get_active_claim_ids(chapter)
    if not active_claims:
        return {"nodes": [], "edges": []}

    query = """
    MATCH (a)-[r]->(b)
    WHERE a.reveal_chapter <= $chapter
      AND b.reveal_chapter <= $chapter
      AND r.reveal_chapter <= $chapter
      AND r.claim_id IN $active_claims
    RETURN a.id, coalesce(a.name, a.title), labels(a),
           b.id, coalesce(b.name, b.title), labels(b),
           type(r), r.claim_id
    LIMIT $limit
    """
    rows = _rows(query, {"chapter": chapter, "active_claims": active_claims, "limit": limit})
    nodes: Dict[str, Dict[str, Any]] = {}
    edges = []
    for r in rows:
        nodes[r[0]] = {"data": {"id": r[0], "label": r[1], "kind": r[2][0]}}
        nodes[r[3]] = {"data": {"id": r[3], "label": r[4], "kind": r[5][0]}}
        edges.append({
            "data": {
                "id": f"{r[0]}_{r[6]}_{r[3]}",
                "source": r[0],
                "target": r[3],
                "label": r[6],
                "claim_id": r[7],
            }
        })

    return {"nodes": list(nodes.values()), "edges": edges}
