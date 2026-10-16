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


def visible_graph(chapter: int, limit: int = 150) -> Dict[str, Any]:
    """Returns all nodes and edges visible at chapter boundary for interactive graph visualization."""
    # 1. Fetch all visible entities (characters, events, locations, factions)
    node_query = """
    MATCH (n)
    WHERE (n:Character OR n:Event OR n:Location OR n:Faction)
      AND n.reveal_chapter <= $chapter
    RETURN n.id, coalesce(n.name, n.title), labels(n), n.reveal_chapter, coalesce(n.role, ''), coalesce(n.aliases, [])
    """
    node_rows = _rows(node_query, {"chapter": chapter})
    nodes: Dict[str, Dict[str, Any]] = {}
    for r in node_rows:
        nodes[r[0]] = {
            "data": {
                "id": r[0],
                "label": r[1],
                "kind": r[2][0] if r[2] else "Entity",
                "reveal_chapter": r[3],
                "role": r[4],
                "aliases": r[5],
            }
        }

    # 2. Fetch all traversable active edges between visible entities
    active_claims = get_active_claim_ids(chapter)
    edges = []
    if active_claims:
        edge_query = """
        MATCH (a)-[r]->(b)
        WHERE a.reveal_chapter <= $chapter
          AND b.reveal_chapter <= $chapter
          AND r.reveal_chapter <= $chapter
          AND r.claim_id IN $active_claims
        RETURN a.id, b.id, type(r), r.claim_id, r.reveal_chapter
        LIMIT $limit
        """
        edge_rows = _rows(edge_query, {"chapter": chapter, "active_claims": active_claims, "limit": limit})
        for r in edge_rows:
            edges.append({
                "data": {
                    "id": f"{r[0]}_{r[2]}_{r[1]}",
                    "source": r[0],
                    "target": r[1],
                    "label": r[2],
                    "claim_id": r[3],
                    "reveal_chapter": r[4],
                }
            })

    return {"nodes": list(nodes.values()), "edges": edges}


def get_node_details(node_id: str, chapter: int) -> Optional[Dict[str, Any]]:
    """Returns detailed case notes, visible incident edges, and supporting evidence for a single node."""
    # 1. Fetch node properties respecting reveal_chapter
    node_q = """
    MATCH (n {id: $id})
    WHERE (n:Character OR n:Event OR n:Location OR n:Faction)
      AND n.reveal_chapter <= $chapter
    RETURN n.id, coalesce(n.name, n.title), labels(n), n.reveal_chapter,
           coalesce(n.role, ''), coalesce(n.aliases, []), coalesce(n.description, ''),
           coalesce(n.event_chapter, null)
    """
    rows = _rows(node_q, {"id": node_id, "chapter": chapter})
    if not rows or not rows[0]:
        return None

    r = rows[0]
    node_data = {
        "id": r[0],
        "name": r[1],
        "kind": r[2][0] if r[2] else "Entity",
        "labels": r[2],
        "reveal_chapter": r[3],
        "role": r[4],
        "aliases": r[5],
        "description": r[6],
        "event_chapter": r[7],
    }

    # 2. Fetch active connected claims and edges
    active_claims = get_active_claim_ids(chapter)
    connections = []
    evidence_list = []
    if active_claims:
        conn_q = """
        MATCH (n {id: $id})-[r]-(target)
        WHERE target.reveal_chapter <= $chapter
          AND r.reveal_chapter <= $chapter
          AND r.claim_id IN $active_claims
        RETURN target.id, coalesce(target.name, target.title), labels(target)[0],
               type(r), r.claim_id, r.reveal_chapter, startNode(r).id = $id AS is_outgoing
        """
        conn_rows = _rows(conn_q, {"id": node_id, "chapter": chapter, "active_claims": active_claims})
        claim_ids = []
        for cr in conn_rows:
            claim_ids.append(cr[4])
            connections.append({
                "target_id": cr[0],
                "target_name": cr[1],
                "target_kind": cr[2],
                "relationship": cr[3],
                "claim_id": cr[4],
                "reveal_chapter": cr[5],
                "direction": "outgoing" if cr[6] else "incoming",
            })

        if claim_ids:
            evi_q = """
            MATCH (e:Evidence)-[:SUPPORTS]->(c:Claim)
            WHERE c.id IN $claim_ids
              AND c.reveal_chapter <= $chapter
              AND e.reveal_chapter <= $chapter
            RETURN c.id, c.text, e.id, e.kind, e.excerpt, e.source_chapter, e.reveal_chapter
            """
            evi_rows = _rows(evi_q, {"claim_ids": claim_ids, "chapter": chapter})
            for er in evi_rows:
                evidence_list.append({
                    "claim_id": er[0],
                    "claim": er[1],
                    "evidence_id": er[2],
                    "kind": er[3],
                    "excerpt": er[4],
                    "source_chapter": er[5],
                    "reveal_chapter": er[6],
                })

    return {
        "node": node_data,
        "connections": connections,
        "evidence": evidence_list,
    }


def get_story_info() -> Dict[str, Any]:
    """Returns general story metadata and maximum chapter boundary."""
    story_q = "MATCH (s:Story) RETURN s.id, s.title, s.description LIMIT 1"
    rows = _rows(story_q)
    if rows and rows[0]:
        return {
            "id": rows[0][0],
            "title": rows[0][1],
            "description": rows[0][2],
            "max_chapters": 8,
        }
    return {
        "id": "glass_orchard",
        "title": "The Glass Orchard",
        "description": "An aristocratic greenhouse estate murder mystery.",
        "max_chapters": 8,
    }
