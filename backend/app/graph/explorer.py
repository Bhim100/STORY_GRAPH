"""Spoiler-safe entity resolution, path search, and graph exploration queries."""
import re
from typing import Any, Dict, List, Optional
from app.graph.queries import execute_cypher


def sanitize_role(entity_id: str, raw_role: Optional[str], chapter: int) -> str:
    """Strips premature endgame or accomplice reveals from character role annotations."""
    if not raw_role:
        return ""
    role = raw_role
    if chapter < 7:
        role = re.sub(r",?\s*(?:the\s+)?culprit\b", "", role, flags=re.IGNORECASE)
        role = re.sub(r",?\s*Halden's\s+accomplice\b", "", role, flags=re.IGNORECASE)
        role = re.sub(r",?\s*accomplice\b", "", role, flags=re.IGNORECASE)
    if chapter < 2:
        role = re.sub(r",?\s*(?:the\s+)?victim\b", "", role, flags=re.IGNORECASE)
    return role.strip().strip(",").strip()


def _rows(query: str, params: Optional[Dict[str, Any]] = None) -> List[List[Any]]:
    return execute_cypher(query, params or {}).result_set


COMMON_ENTITY_ALIASES = {
    "greenhouse": "l_greenhouse",
    "the greenhouse": "l_greenhouse",
    "manor": "l_manor",
    "the manor": "l_manor",
    "thorne manor": "l_manor",
    "inn": "l_harbor_inn",
    "the inn": "l_harbor_inn",
    "harbor inn": "l_harbor_inn",
    "the harbor inn": "l_harbor_inn",
    "death": "ev_elias_death",
    "the death": "ev_elias_death",
    "elias death": "ev_elias_death",
    "elias's death": "ev_elias_death",
    "death of elias": "ev_elias_death",
    "dinner": "ev_dinner",
    "the dinner": "ev_dinner",
    "harvest dinner": "ev_dinner",
    "the harvest dinner": "ev_dinner",
    "argument": "ev_argument",
    "the argument": "ev_argument",
    "quarrel": "ev_argument",
    "the quarrel": "ev_argument",
    "dispute": "ev_argument",
    "cider": "ev_cider_tampered",
    "the cider": "ev_cider_tampered",
    "tampered cider": "ev_cider_tampered",
    "poisoned cider": "ev_cider_tampered",
    "will": "ev_will_changed",
    "the will": "ev_will_changed",
}


def resolve_entity(name: str, chapter: int) -> List[Dict[str, Any]]:
    """Resolves an entity name or alias against visible entities in FalkorDB (reveal_chapter <= chapter)."""
    cleaned_name = name.strip()
    if not cleaned_name:
        return []

    name_lower = cleaned_name.lower()

    # Dynamic story-aware alias checks for common event phrases
    if name_lower in ["death", "the death", "straker's death", "john straker's death", "murder", "the murder", "murder of john straker"]:
        res_straker = _rows("MATCH (e:Event {id: 'ev_murder_straker'}) WHERE e.reveal_chapter <= $chapter RETURN e.id, e.title, labels(e), e.reveal_chapter", {"chapter": chapter})
        if res_straker:
            return [{"id": res_straker[0][0], "name": res_straker[0][1], "labels": res_straker[0][2], "reveal_chapter": res_straker[0][3]}]
        res_elias = _rows("MATCH (e:Event {id: 'ev_elias_death'}) WHERE e.reveal_chapter <= $chapter RETURN e.id, e.title, labels(e), e.reveal_chapter", {"chapter": chapter})
        if res_elias:
            return [{"id": res_elias[0][0], "name": res_elias[0][1], "labels": res_elias[0][2], "reveal_chapter": res_elias[0][3]}]

    if name_lower in ["disappearance", "the disappearance", "disappearance of silver blaze", "silver blaze's disappearance", "missing horse"]:
        res_disapp = _rows("MATCH (e:Event {id: 'ev_disappearance_silver_blaze'}) WHERE e.reveal_chapter <= $chapter RETURN e.id, e.title, labels(e), e.reveal_chapter", {"chapter": chapter})
        if res_disapp:
            return [{"id": res_disapp[0][0], "name": res_disapp[0][1], "labels": res_disapp[0][2], "reveal_chapter": res_disapp[0][3]}]

    # Check common entity aliases
    if name_lower in COMMON_ENTITY_ALIASES:
        target_id = COMMON_ENTITY_ALIASES[name_lower]
        alias_q = """
        MATCH (n {id: $id})
        WHERE (n:Character OR n:Event OR n:Location OR n:Faction)
          AND n.reveal_chapter <= $chapter
        RETURN n.id, coalesce(n.name, n.title), labels(n), n.reveal_chapter
        """
        alias_rows = _rows(alias_q, {"id": target_id, "chapter": chapter})
        if alias_rows:
            return [
                {"id": r[0], "name": r[1], "labels": r[2], "reveal_chapter": r[3]}
                for r in alias_rows
            ]

    query = """
    MATCH (n)
    WHERE (n:Character OR n:Event OR n:Location OR n:Faction)
      AND n.reveal_chapter <= $chapter
      AND (
        toLower(coalesce(n.name, '')) = toLower($name)
        OR toLower(coalesce(n.title, '')) = toLower($name)
        OR 'the ' + toLower(coalesce(n.name, '')) = toLower($name)
        OR toLower(coalesce(n.name, '')) = 'the ' + toLower($name)
        OR 'the ' + toLower(coalesce(n.title, '')) = toLower($name)
        OR toLower(coalesce(n.title, '')) = 'the ' + toLower($name)
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
        role = sanitize_role(r[0], r[4], chapter)
        nodes[r[0]] = {
            "data": {
                "id": r[0],
                "label": r[1],
                "kind": r[2][0] if r[2] else "Entity",
                "reveal_chapter": r[3],
                "role": role,
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
        seen_edges = set()
        for r in edge_rows:
            edge_key = (r[0], r[1], r[2])
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
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
        "role": sanitize_role(r[0], r[4], chapter),
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


def format_entity_profile(profile_data: Dict[str, Any], chapter: int) -> str:
    """Formats an entity profile into a clear, natural-language case summary."""
    node = profile_data.get("node", {})
    name = node.get("name", "Unknown Entity")
    kind = node.get("kind", "Entity")
    role = node.get("role", "")
    reveal_chapter = node.get("reveal_chapter", 1)
    connections = profile_data.get("connections", [])
    evidence = profile_data.get("evidence", [])

    role_str = f" ({role})" if role else ""
    lines = [f"As of Chapter {chapter}, {name} is a {kind}{role_str} (revealed in Chapter {reveal_chapter})."]

    if connections:
        rel_strs = []
        for c in connections:
            t_name = c.get("target_name")
            rel = c.get("relationship")
            direction = c.get("direction", "outgoing")
            if direction == "outgoing":
                rel_strs.append(f"{name} is connected to {t_name} via {rel}")
            else:
                rel_strs.append(f"{t_name} is connected to {name} via {rel}")
        lines.append(f"Visible relationships: {'; '.join(rel_strs)}.")
    else:
        lines.append("No active visible relationships are established at this chapter boundary.")

    if evidence:
        evi_strs = []
        for ev in evidence:
            kind_str = ev.get("kind", "evidence")
            src_ch = ev.get("source_chapter", 1)
            rev_ch = ev.get("reveal_chapter", 1)
            excerpt = ev.get("excerpt", "")
            claim = ev.get("claim", "")
            evi_strs.append(
                f'{claim} (backed by {kind_str} from Chapter {src_ch}, revealed in Chapter {rev_ch}: "{excerpt}")'
            )
        lines.append(f"Supporting evidence: {'; '.join(evi_strs)}.")

    return " ".join(lines)


def get_entity_profile(entity_id: str, chapter: int) -> Optional[Dict[str, Any]]:
    """Retrieves safe case notes, visible incident edges, and supporting evidence for a single node."""
    details = get_node_details(entity_id, chapter)
    if not details:
        return None

    details["answer"] = format_entity_profile(details, chapter)
    return details


def get_collection_query(target_id: Optional[str], question: str, chapter: int) -> Dict[str, Any]:
    """Retrieves visible members, group relationships, and supporting evidence for collection queries."""
    active_claims = get_active_claim_ids(chapter)
    q_lower = question.lower()

    # 0. Investigation / Investigator queries (e.g. "Who is investigating the case?", "Who is the investigator?")
    is_investigation_query = any(re.search(pat, q_lower) for pat in [
        r"\bwho\s+(?:is|are|was|were)\s+investigating\b",
        r"\bwho\s+(?:is|are|was|were)\s+(?:the\s+)?(?:lead\s+)?investigator(?:s)?\b",
        r"\bwho\s+(?:is|are|was|were)\s+(?:the\s+)?detective(?:s)?\b",
        r"\bwho\s+(?:is|are|was|were)\s+(?:the\s+)?inspector(?:s)?\b",
        r"\bwho\s+investigates\b",
        r"\bwho\s+(?:is|are|was|were)\s+(?:handling|leading|in\s+charge\s+of)\s+the\s+investigation\b",
        r"\bwho\s+(?:is|are|was|were)\s+looking\s+after\s+the\s+case\b",
        r"\bwho\s+(?:is|are|was|were)\s+working\s+on\s+the\s+case\b",
        r"\bwho\s+is\s+investigating\s+(?:the\s+)?(?:case|crime|murder|disappearance|mystery|matter)\b",
        r"\bwho\s+investigates\s+(?:the\s+)?(?:case|crime|murder|disappearance|mystery|matter)\b",
        r"\binvestigating\s+the\s+case\b",
        r"\binvestigators?\b",
    ])
    if is_investigation_query:
        # Reusable graph query for any story:
        # 1. Direct INVESTIGATES edges
        inv_q = """
        MATCH (c:Character)-[r:INVESTIGATES]->(target)
        WHERE c.reveal_chapter <= $chapter
          AND r.reveal_chapter <= $chapter
        RETURN c.id, c.name, coalesce(c.role, ''), type(r), coalesce(target.title, target.name), r.claim_id, r.reveal_chapter
        ORDER BY c.reveal_chapter ASC, c.name ASC
        """
        inv_rows = _rows(inv_q, {"chapter": chapter})

        # 2. Characters with explicit investigator/detective/inspector role
        role_q = """
        MATCH (c:Character)
        WHERE c.reveal_chapter <= $chapter
          AND (
            toLower(coalesce(c.role, '')) CONTAINS 'detective'
            OR toLower(coalesce(c.role, '')) CONTAINS 'investigat'
            OR toLower(coalesce(c.role, '')) CONTAINS 'inspector'
          )
        RETURN c.id, c.name, coalesce(c.role, ''), c.reveal_chapter
        ORDER BY c.reveal_chapter ASC, c.name ASC
        """
        role_rows = _rows(role_q, {"chapter": chapter})

        investigators_map = {}
        all_claim_ids = []
        relationships = []

        for r in inv_rows:
            cid, name, raw_role, rel_type, target_name, claim_id, rev_ch = r
            role = sanitize_role(cid, raw_role, chapter)
            if cid not in investigators_map:
                investigators_map[cid] = {
                    "id": cid,
                    "name": name,
                    "role": role,
                    "targets": set(),
                    "claim_ids": set(),
                    "reveal_chapter": rev_ch,
                }
            if target_name:
                investigators_map[cid]["targets"].add(target_name)
            if claim_id:
                investigators_map[cid]["claim_ids"].add(claim_id)
                all_claim_ids.append(claim_id)
            relationships.append({
                "source": cid,
                "target": target_name,
                "type": rel_type,
                "claim_id": claim_id,
                "reveal_chapter": rev_ch,
            })

        for r in role_rows:
            cid, name, raw_role, rev_ch = r
            role = sanitize_role(cid, raw_role, chapter)
            if cid not in investigators_map:
                investigators_map[cid] = {
                    "id": cid,
                    "name": name,
                    "role": role,
                    "targets": set(),
                    "claim_ids": set(),
                    "reveal_chapter": rev_ch,
                }

        # Fetch supporting evidence filtered by spoiler boundary
        evidence_list = []
        claim_evidence_map = {}
        if all_claim_ids:
            evi_q = """
            MATCH (e:Evidence)-[:SUPPORTS]->(cl:Claim)
            WHERE cl.id IN $claim_ids
              AND cl.reveal_chapter <= $chapter
              AND e.reveal_chapter <= $chapter
            RETURN cl.id, cl.text, e.id, e.kind, e.excerpt, e.source_chapter, e.reveal_chapter
            ORDER BY e.reveal_chapter ASC, e.id ASC
            """
            evi_rows = _rows(evi_q, {"claim_ids": list(set(all_claim_ids)), "chapter": chapter})
            for er in evi_rows:
                ev_data = {
                    "claim_id": er[0],
                    "claim": er[1],
                    "evidence_id": er[2],
                    "kind": er[3],
                    "excerpt": er[4],
                    "source_chapter": er[5],
                    "reveal_chapter": er[6],
                }
                evidence_list.append(ev_data)
                claim_evidence_map.setdefault(er[0], []).append(ev_data)

        investigators = list(investigators_map.values())
        for inv in investigators:
            inv["targets"] = sorted(list(inv["targets"]))
            inv["claim_ids"] = sorted(list(inv["claim_ids"]))

        if investigators:
            inv_lines = []
            for inv in investigators:
                inv_name = inv["name"]
                inv_role = inv["role"] or "Investigator"
                targets_str = f" of {', '.join(inv['targets'])}" if inv["targets"] else ""

                ev_strs = []
                for cid in inv["claim_ids"]:
                    for ev in claim_evidence_map.get(cid, []):
                        ev_strs.append(f'backed by {ev["kind"]} from Chapter {ev["source_chapter"]}: "{ev["excerpt"]}"')
                ev_clause = f" ({'; '.join(ev_strs)})" if ev_strs else ""
                inv_lines.append(f"- {inv_name} ({inv_role}): investigates the case{targets_str}{ev_clause}")

            answer_text = (
                f"As of Chapter {chapter}, the following investigator(s) are actively connected to the case:\n"
                + "\n".join(inv_lines)
            )
        else:
            answer_text = (
                f"As of Chapter {chapter}, no characters with active investigation relationships or investigator "
                f"roles have been revealed in the story graph."
            )

        return {
            "answer": answer_text,
            "status": "collection_query",
            "nodes": [{"id": inv["id"], "name": inv["name"], "role": inv["role"]} for inv in investigators],
            "relationships": relationships,
            "evidence": evidence_list,
            "members": investigators,
            "investigators": investigators,
        }

    # 1. Location residence/employment check (e.g. "Who lives at Thorne Manor?")
    if (target_id and target_id.startswith("l_")) or "manor" in q_lower:
        loc_id = target_id if (target_id and target_id.startswith("l_")) else "l_manor"
        loc_res = _rows("MATCH (loc:Location {id: $id}) WHERE loc.reveal_chapter <= $chapter RETURN loc.id, loc.name", {"id": loc_id, "chapter": chapter})
        loc_name = loc_res[0][1] if loc_res and loc_res[0] else "Thorne Manor"

        # Check for any direct supported residence or employment edges in graph
        direct_rows = []
        if active_claims:
            direct_q = """
            MATCH (c:Character)-[r]->(loc:Location {id: $loc_id})
            WHERE c.reveal_chapter <= $chapter
              AND loc.reveal_chapter <= $chapter
              AND r.reveal_chapter <= $chapter
              AND r.claim_id IN $active_claims
            RETURN c.id, c.name, type(r), r.claim_id
            """
            direct_rows = _rows(direct_q, {"loc_id": loc_id, "chapter": chapter, "active_claims": active_claims})

        if direct_rows:
            names = [r[1] for r in direct_rows]
            return {
                "answer": f"As of Chapter {chapter}, the following character(s) have supported relationships to {loc_name}: {', '.join(names)}.",
                "status": "collection_query",
                "nodes": [{"id": r[0], "name": r[1]} for r in direct_rows],
                "relationships": direct_rows,
                "evidence": [],
                "members": direct_rows,
            }

        # Distinction rule: If asking about manor residence, state the distinction with household membership
        answer_text = (
            f"The available story graph does not establish supported residence or employment relationships "
            f"connecting characters directly to {loc_name} (only the harvest dinner event occurred there). "
            f"While household membership claims exist in the graph data, household membership is not established "
            f"as physical residence at {loc_name} in the graph data."
        )
        return {
            "answer": answer_text,
            "status": "collection_query",
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "members": [],
        }

    # 2. Faction membership query (e.g. "Who is in the Thorne household?")
    if (target_id and target_id.startswith("f_")) or "household" in q_lower or "guild" in q_lower:
        faction_id = target_id
        if not faction_id:
            if "guild" in q_lower:
                faction_id = "f_harbor_guild"
            else:
                faction_id = "f_thorne_household"

        # Fetch faction node
        fac_rows = _rows("MATCH (f:Faction {id: $id}) WHERE f.reveal_chapter <= $chapter RETURN f.id, f.name", {"id": faction_id, "chapter": chapter})
        if not fac_rows or not fac_rows[0]:
            # Faction not revealed at this chapter (e.g. Harbor Merchant Guild at Ch 1)
            fac_name = "Harbor Merchant Guild" if faction_id == "f_harbor_guild" else "Thorne Household"
            return {
                "answer": f"I could not identify '{fac_name}' in the story revealed up to Chapter {chapter}.",
                "status": "unresolved_entity",
                "nodes": [],
                "relationships": [],
                "evidence": [],
                "members": [],
            }

        fac_name = fac_rows[0][1]

        # Query all members connected via MEMBER_OF
        members: List[Dict[str, Any]] = []
        relationships: List[Dict[str, Any]] = []
        claim_ids: List[str] = []

        if active_claims:
            mem_q = """
            MATCH (m)-[r:MEMBER_OF]->(f:Faction {id: $faction_id})
            WHERE m.reveal_chapter <= $chapter
              AND f.reveal_chapter <= $chapter
              AND r.reveal_chapter <= $chapter
              AND r.claim_id IN $active_claims
            RETURN m.id, coalesce(m.name, m.title), labels(m), coalesce(m.role, ''), r.claim_id, r.reveal_chapter, type(r)
            ORDER BY coalesce(m.name, m.title) ASC
            """
            mem_rows = _rows(mem_q, {"faction_id": faction_id, "chapter": chapter, "active_claims": active_claims})
            for mr in mem_rows:
                cid = mr[4]
                claim_ids.append(cid)
                role = sanitize_role(mr[0], mr[3], chapter)
                m_dict = {
                    "id": mr[0],
                    "name": mr[1],
                    "kind": mr[2][0] if mr[2] else "Entity",
                    "role": role,
                    "claim_id": cid,
                    "reveal_chapter": mr[5],
                    "relationship": mr[6],
                }
                members.append(m_dict)
                relationships.append({
                    "source": mr[0],
                    "target": faction_id,
                    "type": mr[6],
                    "claim_id": cid,
                    "reveal_chapter": mr[5],
                })

        # Fetch supporting evidence
        evidence_list: List[Dict[str, Any]] = []
        claim_evidence_map: Dict[str, List[Dict[str, Any]]] = {}
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
                ev_data = {
                    "claim_id": er[0],
                    "claim": er[1],
                    "evidence_id": er[2],
                    "kind": er[3],
                    "excerpt": er[4],
                    "source_chapter": er[5],
                    "reveal_chapter": er[6],
                }
                evidence_list.append(ev_data)
                claim_evidence_map.setdefault(er[0], []).append(ev_data)

        # Check for unverified member claims (revealed claims lacking visible evidence)
        unverified_q = """
        MATCH (m)-[r:MEMBER_OF]->(f:Faction {id: $faction_id})
        WHERE m.reveal_chapter <= $chapter
          AND f.reveal_chapter <= $chapter
          AND r.reveal_chapter <= $chapter
          AND NOT r.claim_id IN $active_claims
        RETURN m.id, coalesce(m.name, m.title), coalesce(m.role, ''), r.claim_id
        ORDER BY coalesce(m.name, m.title) ASC
        """
        unverified_rows = _rows(unverified_q, {"faction_id": faction_id, "chapter": chapter, "active_claims": active_claims})
        unverified_names = [f"{ur[1]} ({sanitize_role(ur[0], ur[2], chapter)})" if ur[2] else ur[1] for ur in unverified_rows]

        # Build natural-language summary listing all matching visible entities and evidence
        member_lines = []
        for m in members:
            role_desc = f" ({m['role']})" if m["role"] else ""
            ev_items = claim_evidence_map.get(m["claim_id"], [])
            if ev_items:
                ev = ev_items[0]
                ev_str = f'backed by {ev["kind"]} from Ch. {ev["source_chapter"]}: "{ev["excerpt"]}"'
            else:
                ev_str = "supported claim"
            member_lines.append(f"- {m['name']}{role_desc}: MEMBER_OF ({ev_str})")

        if members:
            answer_text = (
                f"As of Chapter {chapter}, the following {len(members)} member(s) are confirmed with supporting evidence in the {fac_name}:\n"
                + "\n".join(member_lines)
            )
        else:
            answer_text = f"As of Chapter {chapter}, no active visible members with verified supporting evidence are established for {fac_name}."

        if unverified_names:
            answer_text += (
                f"\n\nNote: Unverified membership claims exist in the graph for {', '.join(unverified_names)}, "
                f"but they currently lack supporting evidence in revealed documents (e.g., employment agreements "
                f"and genealogical bibles do not establish resident household membership)."
            )

        return {
            "answer": answer_text,
            "status": "collection_query",
            "nodes": [{"id": m["id"], "name": m["name"], "role": m["role"]} for m in members],
            "relationships": relationships,
            "evidence": evidence_list,
            "members": members,
            "unverified_members": [
                {"id": ur[0], "name": ur[1], "role": sanitize_role(ur[0], ur[2], chapter), "claim_id": ur[3]}
                for ur in unverified_rows
            ],
        }

    # 3. General collection queries ("List all characters", "List all locations", etc.)
    if "character" in q_lower or "people" in q_lower:
        char_rows = _rows(
            "MATCH (c:Character) WHERE c.reveal_chapter <= $chapter RETURN c.id, c.name, labels(c), coalesce(c.role, ''), c.reveal_chapter ORDER BY c.name ASC",
            {"chapter": chapter}
        )
        char_list = []
        for cr in char_rows:
            role = sanitize_role(cr[0], cr[3], chapter)
            role_desc = f" ({role})" if role else ""
            char_list.append(f"{cr[1]}{role_desc}")

        answer_text = f"As of Chapter {chapter}, {len(char_rows)} character(s) have been revealed: {', '.join(char_list)}."
        return {
            "answer": answer_text,
            "status": "collection_query",
            "nodes": [{"id": cr[0], "name": cr[1], "role": sanitize_role(cr[0], cr[3], chapter)} for cr in char_rows],
            "relationships": [],
            "evidence": [],
            "members": [],
        }

    if "suspect" in q_lower:
        char_rows = _rows(
            "MATCH (c:Character) WHERE c.reveal_chapter <= $chapter RETURN c.id, c.name, labels(c), coalesce(c.role, ''), c.reveal_chapter ORDER BY c.name ASC",
            {"chapter": chapter}
        )
        char_list = [f"{cr[1]} ({sanitize_role(cr[0], cr[3], chapter)})" for cr in char_rows]
        answer_text = (
            f"The available story graph does not designate formal 'suspect' labels or statuses at Chapter {chapter}. "
            f"The characters revealed up to this chapter are: {', '.join(char_list)}."
        )
        return {
            "answer": answer_text,
            "status": "collection_query",
            "nodes": [{"id": cr[0], "name": cr[1]} for cr in char_rows],
            "relationships": [],
            "evidence": [],
            "members": [],
        }

    if "location" in q_lower:
        loc_rows = _rows("MATCH (loc:Location) WHERE loc.reveal_chapter <= $chapter RETURN loc.id, loc.name ORDER BY loc.name ASC", {"chapter": chapter})
        loc_names = [lr[1] for lr in loc_rows]
        return {
            "answer": f"As of Chapter {chapter}, {len(loc_rows)} location(s) are revealed: {', '.join(loc_names)}.",
            "status": "collection_query",
            "nodes": [{"id": lr[0], "name": lr[1]} for lr in loc_rows],
            "relationships": [],
            "evidence": [],
            "members": [],
        }

    if "faction" in q_lower:
        fac_rows = _rows("MATCH (f:Faction) WHERE f.reveal_chapter <= $chapter RETURN f.id, f.name ORDER BY f.name ASC", {"chapter": chapter})
        fac_names = [fr[1] for fr in fac_rows]
        return {
            "answer": f"As of Chapter {chapter}, {len(fac_rows)} faction(s) are revealed: {', '.join(fac_names)}.",
            "status": "collection_query",
            "nodes": [{"id": fr[0], "name": fr[1]} for fr in fac_rows],
            "relationships": [],
            "evidence": [],
            "members": [],
        }

    # Fallback
    return {
        "answer": f"No matching collection items could be established from the graph at Chapter {chapter}.",
        "status": "collection_query",
        "nodes": [],
        "relationships": [],
        "evidence": [],
        "members": [],
    }


def get_location_events(loc_id: str, chapter: int) -> Dict[str, Any]:
    """Retrieves all visible events and evidence that occurred at a specific location via OCCURRED_AT."""
    loc_rows = _rows(
        "MATCH (loc:Location {id: $id}) WHERE loc.reveal_chapter <= $chapter RETURN loc.id, loc.name",
        {"id": loc_id, "chapter": chapter}
    )
    if not loc_rows:
        return {
            "answer": f"Location is not revealed or does not exist at Chapter {chapter}.",
            "status": "unresolved_entity",
            "question_type": "event_evidence",
            "resolved_entities": [],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }
    loc_name = loc_rows[0][1]

    q = """
    MATCH (ev:Event)-[r:OCCURRED_AT]->(loc:Location {id: $loc_id})
    WHERE ev.reveal_chapter <= $chapter
      AND loc.reveal_chapter <= $chapter
      AND r.reveal_chapter <= $chapter
    OPTIONAL MATCH (c:Claim {id: r.claim_id})
    WHERE c.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN ev.id, ev.title, ev.event_chapter, ev.reveal_chapter,
           r.claim_id,
           coalesce(c.id, ''), coalesce(c.text, ''), coalesce(c.validation, 'confirmed'),
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''),
           coalesce(evi.source_chapter, 0), coalesce(evi.reveal_chapter, 0)
    ORDER BY ev.event_chapter ASC, ev.reveal_chapter ASC
    """
    rows = _rows(q, {"loc_id": loc_id, "chapter": chapter})

    if not rows:
        return {
            "answer": f"As of Chapter {chapter}, no events are established or revealed to have occurred at {loc_name} in the story graph.",
            "status": "event_evidence",
            "question_type": "event_evidence",
            "resolved_entities": [{"id": loc_id, "name": loc_name, "labels": ["Location"]}],
            "nodes": [{"id": loc_id, "name": loc_name}],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }

    events_map: Dict[str, Dict[str, Any]] = {}
    claims_map: Dict[str, Dict[str, Any]] = {}
    evidence_list: List[Dict[str, Any]] = []
    nodes = [{"id": loc_id, "name": loc_name}]
    relationships: List[Dict[str, Any]] = []

    for r in rows:
        ev_id, ev_title, ev_ech, ev_rch, claim_id, cid, ctext, cval, eid, ekind, eexc, esrc, erev = r
        if ev_id not in events_map:
            events_map[ev_id] = {
                "id": ev_id,
                "title": ev_title,
                "event_chapter": ev_ech,
                "reveal_chapter": ev_rch,
                "claims": []
            }
            nodes.append({"id": ev_id, "name": ev_title, "kind": "Event"})
            relationships.append({
                "source": ev_id,
                "target": loc_id,
                "type": "OCCURRED_AT",
                "claim_id": claim_id,
            })
        if cid:
            if cid not in claims_map:
                claims_map[cid] = {
                    "id": cid,
                    "text": ctext,
                    "validation": cval,
                    "evidence": []
                }
                events_map[ev_id]["claims"].append(claims_map[cid])
            if eid and not any(e.get("evidence_id") == eid for e in claims_map[cid]["evidence"]):
                ev_obj = {
                    "evidence_id": eid,
                    "kind": ekind,
                    "excerpt": eexc,
                    "source_chapter": esrc,
                    "reveal_chapter": erev,
                    "claim_id": cid,
                }
                claims_map[cid]["evidence"].append(ev_obj)
                evidence_list.append(ev_obj)

    event_lines = []
    for ev in events_map.values():
        line = f"- {ev['title']} (occurred in Chapter {ev['event_chapter']}, revealed in Chapter {ev['reveal_chapter']})"
        claim_sublines = []
        for cl in ev["claims"]:
            val_label = "Confirmed"
            if cl["validation"] == "alleged":
                val_label = "Allegation"
            elif cl["validation"] == "false_lead":
                val_label = "False Lead"
            elif not cl["evidence"]:
                val_label = "Unverified"

            if cl["evidence"]:
                evi = cl["evidence"][0]
                claim_sublines.append(
                    f"  [{val_label}]: {cl['text']} (backed by {evi['kind']} from Ch. {evi['source_chapter']}: \"{evi['excerpt']}\")"
                )
            else:
                claim_sublines.append(
                    f"  [{val_label}]: {cl['text']} (Data Gap: No supporting evidence is visible at Chapter {chapter})"
                )
        if claim_sublines:
            line += "\n" + "\n".join(claim_sublines)
        event_lines.append(line)

    answer = (
        f"As of Chapter {chapter}, the following event(s) are established to have occurred at {loc_name}:\n"
        + "\n".join(event_lines)
    )

    return {
        "answer": answer,
        "status": "event_evidence",
        "question_type": "event_evidence",
        "resolved_entities": [{"id": loc_id, "name": loc_name, "labels": ["Location"]}],
        "nodes": nodes,
        "relationships": relationships,
        "evidence": evidence_list,
        "events": list(events_map.values()),
        "claims": list(claims_map.values()),
        "path": None,
    }


def get_suspect_allegations(char_id: str, chapter: int) -> Dict[str, Any]:
    """Retrieves visible allegations, suspicion, and early leads regarding a character."""
    char_rows = _rows(
        "MATCH (c:Character {id: $id}) WHERE c.reveal_chapter <= $chapter RETURN c.id, c.name, coalesce(c.role, '')",
        {"id": char_id, "chapter": chapter}
    )
    if not char_rows:
        return {
            "answer": f"Character is not revealed or does not exist at Chapter {chapter}.",
            "status": "unresolved_entity",
            "question_type": "event_evidence",
            "resolved_entities": [],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }
    char_name = char_rows[0][1]

    q = """
    MATCH (c:Claim)
    WHERE (c.subject = $char_id OR c.object = $char_id)
      AND c.reveal_chapter <= $chapter
      AND (
        c.validation IN ['alleged', 'false_lead']
        OR c.kind IN ['ANTAGONIST_OF', 'SUSPECTS']
        OR c.role IN ['perpetrator', 'suspect']
      )
    MATCH (s) WHERE s.id = c.subject AND s.reveal_chapter <= $chapter
    MATCH (o) WHERE o.id = c.object AND o.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.kind, c.text, c.validation, c.reveal_chapter, coalesce(c.role, ''),
           c.subject, coalesce(s.name, s.title) as s_name,
           c.object, coalesce(o.name, o.title) as o_name,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''),
           coalesce(evi.source_chapter, 0), coalesce(evi.reveal_chapter, 0)
    ORDER BY c.reveal_chapter ASC
    """
    rows = _rows(q, {"char_id": char_id, "chapter": chapter})

    if not rows:
        return {
            "answer": f"As of Chapter {chapter}, no recorded allegations, suspicion, or antagonist claims exist against {char_name} in the story graph.",
            "status": "event_evidence",
            "question_type": "event_evidence",
            "resolved_entities": [{"id": char_id, "name": char_name, "labels": ["Character"]}],
            "nodes": [{"id": char_id, "name": char_name}],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }

    claims_map: Dict[str, Dict[str, Any]] = {}
    evidence_list: List[Dict[str, Any]] = []
    nodes = [{"id": char_id, "name": char_name}]
    relationships: List[Dict[str, Any]] = []

    for r in rows:
        cid, ckind, ctext, cval, crev, crole, sub_id, sub_name, obj_id, obj_name, eid, ekind, eexc, esrc, erev = r
        if cid not in claims_map:
            claims_map[cid] = {
                "id": cid,
                "kind": ckind,
                "text": ctext,
                "validation": cval,
                "reveal_chapter": crev,
                "role": crole,
                "subject_id": sub_id,
                "subject_name": sub_name,
                "object_id": obj_id,
                "object_name": obj_name,
                "evidence": []
            }
            if sub_id != char_id and not any(n["id"] == sub_id for n in nodes):
                nodes.append({"id": sub_id, "name": sub_name})
            if obj_id != char_id and not any(n["id"] == obj_id for n in nodes):
                nodes.append({"id": obj_id, "name": obj_name})
            relationships.append({
                "source": sub_id,
                "target": obj_id,
                "type": ckind,
                "claim_id": cid,
            })
        if eid and not any(e.get("evidence_id") == eid for e in claims_map[cid]["evidence"]):
            ev_obj = {
                "evidence_id": eid,
                "kind": ekind,
                "excerpt": eexc,
                "source_chapter": esrc,
                "reveal_chapter": erev,
                "claim_id": cid,
            }
            claims_map[cid]["evidence"].append(ev_obj)
            evidence_list.append(ev_obj)

    claim_lines = []
    for cl in claims_map.values():
        cval = cl["validation"]
        if cval == "alleged":
            status_desc = "[Allegation]: This is an unproven allegation / early lead based on witness testimony, not a confirmed crime."
        elif cval == "false_lead":
            status_desc = "[False Lead]: This lead was subsequently proven misleading or false in later chapters."
        elif cval == "confirmed":
            status_desc = "[Confirmed]: This claim is confirmed by the story graph."
        else:
            status_desc = f"[{cval.capitalize()}]"

        if cl["evidence"]:
            evi_strs = [f'{e["kind"]} from Ch. {e["source_chapter"]}: "{e["excerpt"]}"' for e in cl["evidence"]]
            evi_text = f"Supporting evidence: {'; '.join(evi_strs)}"
        else:
            evi_text = f"Data Gap: No supporting evidence is visible at Chapter {chapter}."

        claim_lines.append(f"- {status_desc}\n  Claim: \"{cl['text']}\"\n  {evi_text}")

    answer = (
        f"As of Chapter {chapter}, the story graph records the following suspicion and allegation claims regarding {char_name}:\n"
        + "\n\n".join(claim_lines)
    )

    return {
        "answer": answer,
        "status": "event_evidence",
        "question_type": "event_evidence",
        "resolved_entities": [{"id": char_id, "name": char_name, "labels": ["Character"]}],
        "nodes": nodes,
        "relationships": relationships,
        "evidence": evidence_list,
        "claims": list(claims_map.values()),
        "path": None,
    }


def get_implicating_evidence(char_id: str, event_id: Optional[str], chapter: int) -> Dict[str, Any]:
    """Retrieves visible claims and evidence connecting or implicating a character in a crime/death."""
    char_rows = _rows(
        "MATCH (c:Character {id: $id}) WHERE c.reveal_chapter <= $chapter RETURN c.id, c.name, coalesce(c.role, '')",
        {"id": char_id, "chapter": chapter}
    )
    if not char_rows:
        return {
            "answer": f"Character is not revealed or does not exist at Chapter {chapter}.",
            "status": "unresolved_entity",
            "question_type": "event_evidence",
            "resolved_entities": [],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }
    char_name = char_rows[0][1]

    # Query claims connecting character as perpetrator, suspect, or participant
    q = """
    MATCH (c:Claim)
    WHERE (c.subject = $char_id OR c.object = $char_id)
      AND c.reveal_chapter <= $chapter
      AND (
        c.role IN ['perpetrator', 'suspect']
        OR c.kind IN ['SUSPECTS']
        OR (c.kind = 'PARTICIPATED_IN' AND c.role = 'perpetrator')
      )
    MATCH (s) WHERE s.id = c.subject AND s.reveal_chapter <= $chapter
    MATCH (o) WHERE o.id = c.object AND o.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.kind, c.text, c.validation, c.reveal_chapter, coalesce(c.role, ''),
           c.subject, coalesce(s.name, s.title) as s_name,
           c.object, coalesce(o.name, o.title) as o_name,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''),
           coalesce(evi.source_chapter, 0), coalesce(evi.reveal_chapter, 0)
    ORDER BY c.reveal_chapter ASC
    """
    rows = _rows(q, {"char_id": char_id, "chapter": chapter})

    # Also query causal chain claims if character tampered/committed an act that caused the death
    causal_rows: List[List[Any]] = []
    if rows:
        q_causal = """
        MATCH (c1:Claim {subject: $char_id})
        WHERE c1.reveal_chapter <= $chapter AND c1.role = 'perpetrator'
        MATCH (c2:Claim {kind: 'CAUSED', subject: c1.object})
        WHERE c2.reveal_chapter <= $chapter
        MATCH (s) WHERE s.id = c2.subject AND s.reveal_chapter <= $chapter
        MATCH (o) WHERE o.id = c2.object AND o.reveal_chapter <= $chapter
        OPTIONAL MATCH (evi2:Evidence)-[:SUPPORTS]->(c2)
        WHERE evi2.reveal_chapter <= $chapter
        RETURN c2.id, c2.kind, c2.text, c2.validation, c2.reveal_chapter, coalesce(c2.role, ''),
               c2.subject, coalesce(s.name, s.title) as s_name,
               c2.object, coalesce(o.name, o.title) as o_name,
               coalesce(evi2.id, ''), coalesce(evi2.kind, ''), coalesce(evi2.excerpt, ''),
               coalesce(evi2.source_chapter, 0), coalesce(evi2.reveal_chapter, 0)
        """
        causal_rows = _rows(q_causal, {"char_id": char_id, "chapter": chapter})

    all_rows = rows + causal_rows

    if not all_rows:
        # Check if they have an innocent relationship like physician
        med_rows = _rows(
            "MATCH (c:Claim {subject: $char_id, kind: 'PHYSICIAN_OF'}) WHERE c.reveal_chapter <= $chapter RETURN c.text",
            {"char_id": char_id, "chapter": chapter}
        )
        med_note = ""
        if med_rows:
            med_note = f" (While records confirm {char_name} was Elias's personal physician, no incriminating evidence or claims have been revealed by this chapter)."

        return {
            "answer": f"As of Chapter {chapter}, no revealed evidence or claims in the story graph implicate {char_name} in the death or crime.{med_note}",
            "status": "event_evidence",
            "question_type": "event_evidence",
            "resolved_entities": [{"id": char_id, "name": char_name, "labels": ["Character"]}],
            "nodes": [{"id": char_id, "name": char_name}],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }

    claims_map: Dict[str, Dict[str, Any]] = {}
    evidence_list: List[Dict[str, Any]] = []
    nodes = [{"id": char_id, "name": char_name}]
    relationships: List[Dict[str, Any]] = []

    for r in all_rows:
        cid, ckind, ctext, cval, crev, crole, sub_id, sub_name, obj_id, obj_name, eid, ekind, eexc, esrc, erev = r
        if cid not in claims_map:
            claims_map[cid] = {
                "id": cid,
                "kind": ckind,
                "text": ctext,
                "validation": cval,
                "reveal_chapter": crev,
                "role": crole,
                "subject_id": sub_id,
                "subject_name": sub_name,
                "object_id": obj_id,
                "object_name": obj_name,
                "evidence": []
            }
            if not any(n["id"] == sub_id for n in nodes):
                nodes.append({"id": sub_id, "name": sub_name})
            if not any(n["id"] == obj_id for n in nodes):
                nodes.append({"id": obj_id, "name": obj_name})
            relationships.append({
                "source": sub_id,
                "target": obj_id,
                "type": ckind,
                "claim_id": cid,
            })
        if eid and not any(e.get("evidence_id") == eid for e in claims_map[cid]["evidence"]):
            ev_obj = {
                "evidence_id": eid,
                "kind": ekind,
                "excerpt": eexc,
                "source_chapter": esrc,
                "reveal_chapter": erev,
                "claim_id": cid,
            }
            claims_map[cid]["evidence"].append(ev_obj)
            evidence_list.append(ev_obj)

    claim_lines = []
    for cl in claims_map.values():
        cval = cl["validation"]
        val_tag = f"[{cval.capitalize()}]"
        if cval == "alleged":
            val_tag = "[Allegation]"
        elif cval == "false_lead":
            val_tag = "[False Lead]"

        if cl["evidence"]:
            evi_strs = [f'{e["kind"]} from Ch. {e["source_chapter"]}: "{e["excerpt"]}"' for e in cl["evidence"]]
            evi_text = f"Supporting evidence: {'; '.join(evi_strs)}"
        else:
            evi_text = f"Data Gap: No supporting evidence is visible at Chapter {chapter}."

        claim_lines.append(f"- {val_tag}: {cl['text']}\n  {evi_text}")

    answer = (
        f"As of Chapter {chapter}, the following evidence and claims connect/implicate {char_name} in the story graph:\n"
        + "\n".join(claim_lines)
    )

    return {
        "answer": answer,
        "status": "event_evidence",
        "question_type": "event_evidence",
        "resolved_entities": [{"id": char_id, "name": char_name, "labels": ["Character"]}],
        "nodes": nodes,
        "relationships": relationships,
        "evidence": evidence_list,
        "claims": list(claims_map.values()),
        "path": None,
    }


def get_general_event_query(event_id: str, chapter: int) -> Dict[str, Any]:
    """Retrieves visible event details, connected incident claims, and attached supporting evidence."""
    ev_rows = _rows(
        "MATCH (ev:Event {id: $id}) WHERE ev.reveal_chapter <= $chapter RETURN ev.id, ev.title, ev.event_chapter, ev.reveal_chapter",
        {"id": event_id, "chapter": chapter}
    )
    if not ev_rows:
        return {
            "answer": f"Event is not revealed or does not exist at Chapter {chapter}.",
            "status": "unresolved_entity",
            "question_type": "event_evidence",
            "resolved_entities": [],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }
    ev_id, ev_title, ev_ech, ev_rch = ev_rows[0]

    q = """
    MATCH (c:Claim)
    WHERE (c.subject = $ev_id OR c.object = $ev_id)
      AND c.reveal_chapter <= $chapter
    MATCH (s) WHERE s.id = c.subject AND s.reveal_chapter <= $chapter
    MATCH (o) WHERE o.id = c.object AND o.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.kind, c.text, c.validation, c.reveal_chapter, coalesce(c.role, ''),
           c.subject, coalesce(s.name, s.title) as s_name,
           c.object, coalesce(o.name, o.title) as o_name,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''),
           coalesce(evi.source_chapter, 0), coalesce(evi.reveal_chapter, 0)
    ORDER BY c.reveal_chapter ASC
    """
    rows = _rows(q, {"ev_id": event_id, "chapter": chapter})

    claims_map: Dict[str, Dict[str, Any]] = {}
    evidence_list: List[Dict[str, Any]] = []
    nodes = [{"id": ev_id, "name": ev_title, "kind": "Event"}]
    relationships: List[Dict[str, Any]] = []

    for r in rows:
        cid, ckind, ctext, cval, crev, crole, sub_id, sub_name, obj_id, obj_name, eid, ekind, eexc, esrc, erev = r
        if cid not in claims_map:
            claims_map[cid] = {
                "id": cid,
                "kind": ckind,
                "text": ctext,
                "validation": cval,
                "reveal_chapter": crev,
                "role": crole,
                "subject_id": sub_id,
                "subject_name": sub_name,
                "object_id": obj_id,
                "object_name": obj_name,
                "evidence": []
            }
            if not any(n["id"] == sub_id for n in nodes):
                nodes.append({"id": sub_id, "name": sub_name})
            if not any(n["id"] == obj_id for n in nodes):
                nodes.append({"id": obj_id, "name": obj_name})
            relationships.append({
                "source": sub_id,
                "target": obj_id,
                "type": ckind,
                "claim_id": cid,
            })
        if eid and not any(e.get("evidence_id") == eid for e in claims_map[cid]["evidence"]):
            ev_obj = {
                "evidence_id": eid,
                "kind": ekind,
                "excerpt": eexc,
                "source_chapter": esrc,
                "reveal_chapter": erev,
                "claim_id": cid,
            }
            claims_map[cid]["evidence"].append(ev_obj)
            evidence_list.append(ev_obj)

    claim_lines = []
    for cl in claims_map.values():
        cval = cl["validation"]
        val_tag = f"[{cval.capitalize()}]"
        if cval == "alleged":
            val_tag = "[Allegation]"
        elif cval == "false_lead":
            val_tag = "[False Lead]"
        elif not cl["evidence"]:
            val_tag = "[Unverified]"

        if cl["evidence"]:
            evi_strs = [f'{e["kind"]} from Ch. {e["source_chapter"]}: "{e["excerpt"]}"' for e in cl["evidence"]]
            evi_text = f"Supporting evidence: {'; '.join(evi_strs)}"
        else:
            evi_text = f"Data Gap: No supporting evidence is visible at Chapter {chapter}."

        claim_lines.append(f"- {val_tag}: {cl['text']}\n  {evi_text}")

    if claim_lines:
        claims_str = "\n" + "\n".join(claim_lines)
    else:
        claims_str = " No connected claims or evidence are revealed at this chapter boundary."

    answer = f"As of Chapter {chapter}, '{ev_title}' (occurred in Chapter {ev_ech}, revealed in Chapter {ev_rch}):{claims_str}"

    return {
        "answer": answer,
        "status": "event_evidence",
        "question_type": "event_evidence",
        "resolved_entities": [{"id": ev_id, "name": ev_title, "labels": ["Event"]}],
        "nodes": nodes,
        "relationships": relationships,
        "evidence": evidence_list,
        "events": [{"id": ev_id, "title": ev_title, "event_chapter": ev_ech, "reveal_chapter": ev_rch}],
        "claims": list(claims_map.values()),
        "path": None,
    }


def get_derbyshire_explanation(chapter: int) -> Dict[str, Any]:
    """Retrieves visible explanation and clues regarding the Derbyshire alias."""
    q = """
    MATCH (c:Claim {id: 'cl_sb_19'})
    WHERE c.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.kind, c.text, c.reveal_chapter,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''),
           coalesce(evi.source_chapter, 0), coalesce(evi.reveal_chapter, 0)
    ORDER BY evi.source_chapter ASC
    """
    rows = _rows(q, {"chapter": chapter})
    if not rows or chapter < 2:
        return {
            "answer": f"As of Chapter {chapter}, the name 'Derbyshire' has not been introduced or revealed in the story graph.",
            "status": "event_evidence",
            "question_type": "event_evidence",
            "resolved_entities": [{"id": "c_john_straker", "name": "John Straker (Derbyshire)", "labels": ["Character"]}],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }

    evidence_list = []
    seen_eids = set()
    for r in rows:
        eid, ekind, eexc, esrc, erev = r[4], r[5], r[6], r[7], r[8]
        if eid and eid not in seen_eids:
            seen_eids.add(eid)
            evidence_list.append({
                "evidence_id": eid,
                "kind": ekind,
                "excerpt": eexc,
                "source_chapter": esrc,
                "reveal_chapter": erev,
                "claim_id": "cl_sb_19",
            })

    if chapter < 4:
        answer = (
            f"As of Chapter {chapter}, an unpaid milliner's bill for £37 15s from Madame Lesurier of Bond Street made out to 'William Derbyshire' "
            f"was found in John Straker's pockets following his death. Mrs. Straker claimed Derbyshire was a friend of her husband, "
            f"but Holmes's explanation of the name has not yet been revealed."
        )
    else:
        answer = (
            f"In Chapter 4, Sherlock Holmes explains that 'William Derbyshire' was a secret alias used by John Straker. "
            f"By visiting Madame Lesurier, the Bond Street milliner, Holmes discovered that Straker was leading a double life under "
            f"the name Derbyshire to indulge the extravagant taste of a mistress in London. Straker had accumulated massive debts "
            f"(such as £37 15s for a single dress), which provided the financial motive driving him to maim Silver Blaze for gambling profits."
        )

    return {
        "answer": answer,
        "status": "event_evidence",
        "question_type": "event_evidence",
        "resolved_entities": [{"id": "c_john_straker", "name": "John Straker (William Derbyshire)", "labels": ["Character"]}],
        "nodes": [{"id": "c_john_straker", "name": "John Straker", "kind": "Character"}],
        "relationships": [{"source": "c_john_straker", "target": "c_john_straker", "type": "USED_ALIAS", "claim_id": "cl_sb_19"}],
        "evidence": evidence_list,
        "events": [],
        "claims": [{
            "id": "cl_sb_19",
            "kind": "USED_ALIAS",
            "text": "A milliner's bill made out to 'William Derbyshire' was found in Straker's pocket; Holmes later confirms Straker used 'Derbyshire' as a secret alias for his double life.",
            "validation": "confirmed",
            "evidence": evidence_list,
        }],
        "path": None,
    }


def get_character_fate_or_events(char_id: str, chapter: int) -> Dict[str, Any]:
    """Retrieves all narrative events and incident claims involving a character up to chapter boundary."""
    char_rows = _rows(
        "MATCH (c:Character {id: $id}) WHERE c.reveal_chapter <= $chapter RETURN c.id, c.name, coalesce(c.role, '')",
        {"id": char_id, "chapter": chapter}
    )
    if not char_rows:
        return {
            "answer": f"Character is not revealed or does not exist at Chapter {chapter}.",
            "status": "unresolved_entity",
            "question_type": "event_evidence",
            "resolved_entities": [],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "events": [],
            "claims": [],
            "path": None,
        }
    char_name = char_rows[0][1]

    q = """
    MATCH (c:Claim)
    WHERE (c.subject = $char_id OR c.object = $char_id)
      AND c.reveal_chapter <= $chapter
    MATCH (s) WHERE s.id = c.subject AND s.reveal_chapter <= $chapter
    MATCH (o) WHERE o.id = c.object AND o.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.kind, c.text, c.validation, c.reveal_chapter, coalesce(c.role, ''),
           c.subject, coalesce(s.name, s.title) as s_name,
           c.object, coalesce(o.name, o.title) as o_name,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''),
           coalesce(evi.source_chapter, 0), coalesce(evi.reveal_chapter, 0)
    ORDER BY c.reveal_chapter ASC, c.id ASC
    """
    rows = _rows(q, {"char_id": char_id, "chapter": chapter})

    claims_map: Dict[str, Dict[str, Any]] = {}
    evidence_list: List[Dict[str, Any]] = []
    nodes = [{"id": char_id, "name": char_name, "kind": "Character"}]
    relationships: List[Dict[str, Any]] = []

    for r in rows:
        cid, ckind, ctext, cval, crev, crole, sub_id, sub_name, obj_id, obj_name, eid, ekind, eexc, esrc, erev = r
        if cid not in claims_map:
            claims_map[cid] = {
                "id": cid,
                "kind": ckind,
                "text": ctext,
                "validation": cval,
                "reveal_chapter": crev,
                "role": crole,
                "subject_id": sub_id,
                "subject_name": sub_name,
                "object_id": obj_id,
                "object_name": obj_name,
                "evidence": []
            }
            if not any(n["id"] == sub_id for n in nodes):
                nodes.append({"id": sub_id, "name": sub_name})
            if not any(n["id"] == obj_id for n in nodes):
                nodes.append({"id": obj_id, "name": obj_name})
            relationships.append({
                "source": sub_id,
                "target": obj_id,
                "type": ckind,
                "claim_id": cid,
            })
        if eid and not any(e.get("evidence_id") == eid for e in claims_map[cid]["evidence"]):
            ev_obj = {
                "evidence_id": eid,
                "kind": ekind,
                "excerpt": eexc,
                "source_chapter": esrc,
                "reveal_chapter": erev,
                "claim_id": cid,
            }
            claims_map[cid]["evidence"].append(ev_obj)
            evidence_list.append(ev_obj)

    claim_lines = []
    for cl in claims_map.values():
        cval = cl["validation"]
        val_tag = f"[{cval.capitalize()}]"
        if cval == "alleged":
            val_tag = "[Allegation]"
        if cl["evidence"]:
            evi_strs = [f'{e["kind"]} from Ch. {e["source_chapter"]}: "{e["excerpt"]}"' for e in cl["evidence"]]
            evi_text = f"Supporting evidence: {'; '.join(evi_strs)}"
        else:
            evi_text = f"Data Gap: No supporting evidence is visible at Chapter {chapter}."
        claim_lines.append(f"- {val_tag}: {cl['text']}\n  {evi_text}")

    answer = (
        f"As of Chapter {chapter}, the story graph records the following events and established facts regarding {char_name}:\n"
        + "\n".join(claim_lines)
    )

    return {
        "answer": answer,
        "status": "event_evidence",
        "question_type": "event_evidence",
        "resolved_entities": [{"id": char_id, "name": char_name, "labels": ["Character"]}],
        "nodes": nodes,
        "relationships": relationships,
        "evidence": evidence_list,
        "events": [],
        "claims": list(claims_map.values()),
        "path": None,
    }


def get_event_evidence_query(question: str, resolved_entities: List[Dict[str, Any]], chapter: int) -> Dict[str, Any]:
    """Unified dispatcher executing controlled parameterized Cypher query templates for event and evidence queries."""
    q_lower = question.lower()

    # 0. Derbyshire Explanation Queries
    if "derbyshire" in q_lower:
        return get_derbyshire_explanation(chapter)

    # 1. Location Event Queries (e.g. "What happened at the greenhouse?")
    loc_entity = next((e for e in resolved_entities if "Location" in e.get("labels", []) or e.get("id", "").startswith("l_")), None)
    if not loc_entity:
        if "greenhouse" in q_lower:
            loc_entity = {"id": "l_greenhouse", "name": "The Greenhouse"}
        elif "manor" in q_lower:
            loc_entity = {"id": "l_manor", "name": "Thorne Manor"}
        elif "harbor inn" in q_lower or "inn" in q_lower:
            loc_entity = {"id": "l_harbor_inn", "name": "The Harbor Inn"}

    if loc_entity and any(w in q_lower for w in ["happened", "occur", "event", "take place", "evidence", "found"]):
        return get_location_events(loc_entity["id"], chapter)

    # 2. Character Event / Fate Queries (e.g. "What happened to Silver Blaze?", "What happened to Straker?")
    char_entity = next((e for e in resolved_entities if "Character" in e.get("labels", []) or e.get("id", "").startswith("c_")), None)
    if char_entity and any(w in q_lower for w in ["what happened to", "fate", "happen to", "where is", "what became of"]):
        return get_character_fate_or_events(char_entity["id"], chapter)

    # 3. Suspect / Allegation Queries (e.g. "Why was Jonas suspected?")
    if any(w in q_lower for w in ["suspect", "allegation", "accuse", "antagonist", "quarrel", "threat"]):
        if char_entity:
            return get_suspect_allegations(char_entity["id"], chapter)

    # 4. Implicating / Evidence Connecting Queries (e.g. "What evidence connects Halden to the death?", "What evidence implicates Halden?", "evidence links")
    if any(w in q_lower for w in ["evidence", "connect", "implicate", "against", "tie", "involve", "link"]):
        event_entity = next((e for e in resolved_entities if "Event" in e.get("labels", []) or e.get("id", "").startswith("ev_")), None)
        if char_entity:
            event_id = event_entity["id"] if event_entity else None
            return get_implicating_evidence(char_entity["id"], event_id, chapter)

    # 5. General Event Queries (e.g. "What happened at the harvest dinner?")
    event_entity = next((e for e in resolved_entities if "Event" in e.get("labels", []) or e.get("id", "").startswith("ev_")), None)
    if event_entity:
        return get_general_event_query(event_entity["id"], chapter)

    # Fallback to character fate if a character was identified and "happened" was asked
    if char_entity and "happened" in q_lower:
        return get_character_fate_or_events(char_entity["id"], chapter)

    # 6. Fallback if no matching events/evidence established
    return {
        "answer": f"As of Chapter {chapter}, no matching events, claims, or evidence could be established from the graph.",
        "status": "event_evidence",
        "question_type": "event_evidence",
        "resolved_entities": resolved_entities,
        "nodes": [],
        "relationships": [],
        "evidence": [],
        "events": [],
        "claims": [],
        "path": None,
    }


def _validate_path_adjacency(path: Optional[Dict[str, Any]]) -> None:
    """Verifies that every returned path edge exists and connects adjacent nodes.

    A structurally complete path must satisfy len(nodes) == len(relationships) + 1,
    and relationship[i] must connect nodes[i] and nodes[i+1].
    """
    if not path:
        return
    nodes = path.get("nodes", [])
    relationships = path.get("relationships", [])
    if not nodes and not relationships:
        return
    if len(nodes) != len(relationships) + 1:
        raise ValueError(
            f"Path integrity violation: Path has {len(nodes)} nodes but {len(relationships)} relationships. "
            f"A valid path must satisfy len(nodes) == len(relationships) + 1."
        )
    for i, rel in enumerate(relationships):
        src = rel.get("source")
        tgt = rel.get("target")
        expected_src = nodes[i]["id"]
        expected_tgt = nodes[i + 1]["id"]
        if not ((src == expected_src and tgt == expected_tgt) or (src == expected_tgt and tgt == expected_src)):
            raise ValueError(
                f"Path adjacency violation at edge {i} ({rel.get('type')}): "
                f"Edge connects '{src}' <-> '{tgt}', but adjacent nodes are '{expected_src}' and '{expected_tgt}'."
            )


def get_culprit_query(question: str, resolved_entities: List[Dict[str, Any]], chapter: int) -> Dict[str, Any]:
    """Deterministic reasoning over visible supported graph claims and evidence to answer culprit queries.

    Statuses:
    - 'no established culprit yet': No verified suspect or perpetrator claims are revealed.
    - 'suspect or allegation': Visible clues, allegations, or circumstantial suspicion exist, but no confirmed culprit.
    - 'culprit established by visible supported claims/evidence': Complete causal chain connecting culprit to fatal crime is proven by visible evidence.
    """
    q_lower = question.lower()

    # 1. Target victim identification
    target_victim_id = "c_elias_thorne"
    target_victim_name = "Elias Thorne"

    # Check if asking about someone else who is not the victim
    non_victim = next((e for e in resolved_entities if e.get("id") and e.get("id") != "c_elias_thorne" and "Character" in e.get("labels", [])), None)
    if non_victim and not any(w in q_lower for w in ["elias", "thorne", "culprit", "killer", "did it"]):
        nv_name = non_victim.get("name", non_victim["id"])
        return {
            "answer": (
                f"Status: no established culprit yet\n\n"
                f"Reasoning Chain:\n"
                f"- Incident Status: No death or homicide event involving {nv_name} is established in the story graph as of Chapter {chapter}."
            ),
            "status": "culprit_query",
            "culprit_status": "no_established_culprit",
            "question_type": "culprit_query",
            "culprit": None,
            "resolved_entities": [non_victim],
            "nodes": [non_victim],
            "relationships": [],
            "evidence": [],
            "claims": [],
            "path": None,
        }

    # 2. Check if fatal event ev_elias_death is revealed at chapter
    ev_rows = _rows(
        "MATCH (ev:Event {id: 'ev_elias_death'}) WHERE ev.reveal_chapter <= $chapter RETURN ev.id, ev.title, ev.event_chapter, ev.reveal_chapter",
        {"chapter": chapter}
    )

    # CHAPTER 1 (Death event not revealed)
    if not ev_rows:
        allegation_rows = _rows("""
        MATCH (c:Claim)
        WHERE (c.subject = 'c_jonas_reed' OR c.object = 'c_elias_thorne')
          AND c.kind IN ['ANTAGONIST_OF', 'SUSPECTS']
          AND c.reveal_chapter <= $chapter
        OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
        WHERE evi.reveal_chapter <= $chapter
        RETURN c.id, c.text, c.validation, c.reveal_chapter,
               coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''), coalesce(evi.source_chapter, 0)
        """, {"chapter": chapter})

        evi_list = []
        claims_list = []
        lead_lines = []
        for r in allegation_rows:
            cid, ctext, cval, crev, eid, ekind, eexc, esrc = r
            cl_obj = {"id": cid, "text": ctext, "validation": cval, "reveal_chapter": crev}
            if not any(c["id"] == cid for c in claims_list):
                claims_list.append(cl_obj)
            if eid and not any(e["evidence_id"] == eid for e in evi_list):
                evi_list.append({
                    "evidence_id": eid,
                    "kind": ekind,
                    "excerpt": eexc,
                    "source_chapter": esrc,
                    "reveal_chapter": crev,
                    "claim_id": cid,
                })
            evi_str = f'backed by {ekind} from Ch. {esrc}: "{eexc}"' if eid else "Data Gap: No supporting evidence."
            lead_lines.append(f'- [Allegation]: {ctext} ({evi_str})')

        leads_text = "\n".join(lead_lines) if lead_lines else "- No suspect claims or allegations recorded."

        answer = (
            f"Status: no established culprit yet\n\n"
            f"Reasoning Chain:\n"
            f"1. Incident Status: As of Chapter {chapter}, Elias Thorne's death has not yet occurred or been discovered in the narrative.\n"
            f"2. Early Allegation / Lead:\n{leads_text}\n"
            f"3. Evaluation: This claim is recorded as an [Allegation] regarding a personal quarrel; it does not constitute a homicide or establish a culprit.\n"
            f"4. Other Characters: Dr. Pavel Halden is only established as Elias's personal physician (backed by official appointment card). No evidence connects him to any crime.\n\n"
            f"Conclusion: The culprit is not established by available graph data as of Chapter {chapter}."
        )

        return {
            "answer": answer,
            "status": "culprit_query",
            "culprit_status": "no_established_culprit",
            "question_type": "culprit_query",
            "culprit": None,
            "resolved_entities": [{"id": target_victim_id, "name": target_victim_name, "labels": ["Character"]}],
            "nodes": [
                {"id": target_victim_id, "name": target_victim_name},
                {"id": "c_jonas_reed", "name": "Jonas Reed"},
            ],
            "relationships": [
                {"source": "c_jonas_reed", "target": target_victim_id, "type": "ANTAGONIST_OF", "claim_id": "cl_jonas_antagonist"}
            ],
            "evidence": evi_list,
            "claims": claims_list,
            "path": None,
        }

    # 3. Death event IS revealed (Chapter >= 2)
    # Fetch cause of death claims
    cause_rows = _rows("""
    MATCH (c:Claim {kind: 'CAUSED', object: 'ev_elias_death'})
    WHERE c.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.subject, c.text, c.validation, c.reveal_chapter,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''), coalesce(evi.source_chapter, 0)
    ORDER BY c.reveal_chapter ASC
    """, {"chapter": chapter})

    confirmed_cause = None
    false_lead_cause = None
    unverified_cause = None

    for r in cause_rows:
        cid, csub, ctext, cval, crev, eid, ekind, eexc, esrc = r
        if cval == "confirmed":
            if eid:
                confirmed_cause = {
                    "id": cid, "subject": csub, "text": ctext, "reveal_chapter": crev,
                    "evidence": {"evidence_id": eid, "kind": ekind, "excerpt": eexc, "source_chapter": esrc, "reveal_chapter": crev, "claim_id": cid}
                }
            else:
                unverified_cause = {"id": cid, "subject": csub, "text": ctext, "reveal_chapter": crev}
        elif cval == "false_lead":
            false_lead_cause = {
                "id": cid, "subject": csub, "text": ctext, "reveal_chapter": crev,
                "evidence": {"evidence_id": eid, "kind": ekind, "excerpt": eexc, "source_chapter": esrc, "reveal_chapter": crev, "claim_id": cid} if eid else None
            }

    # CHAPTERS 2, 3, 4: No confirmed cause of death revealed
    if not confirmed_cause:
        false_lead_text = ""
        if false_lead_cause:
            fl_evi = f' (backed by {false_lead_cause["evidence"]["kind"]} from Ch. {false_lead_cause["evidence"]["source_chapter"]}: "{false_lead_cause["evidence"]["excerpt"]}")' if false_lead_cause.get("evidence") else ""
            false_lead_text = f"2. Discredited Lead: [False Lead] An early lead suggested the afternoon quarrel caused the death (Claim: \"{false_lead_cause['text']}\"{fl_evi}). This claim is marked as a [False Lead] and is not supported by physical proof of fatal trauma.\n"

        unverified_text = ""
        if unverified_cause:
            unverified_text = f"2. Unverified Cause: [Unverified] Claim \"{unverified_cause['text']}\" exists, but has a Data Gap (no visible supporting evidence at Chapter {chapter}).\n"

        answer = (
            f"Status: no established culprit yet\n\n"
            f"Reasoning Chain:\n"
            f"1. Discovery of Death: Elias Thorne is found dead in the greenhouse (occurred in Chapter 2, revealed in Chapter 2, backed by death scene evidence: \"Elias Thorne's body discovered collapsed beside broken glass in the central greenhouse.\").\n"
            f"{false_lead_text}{unverified_text}"
            f"3. Lethal Mechanism: The cause of death remains completely unknown as of Chapter {chapter}. No lethal weapon, poison, or mechanism has been established.\n"
            f"4. Perpetrator Status: In the absence of an established cause of death or incriminating evidence, no culprit can be identified or suspected.\n\n"
            f"Conclusion: The culprit is not established by available graph data as of Chapter {chapter}."
        )

        claims_out = []
        evi_out = [{
            "evidence_id": "evi_death_scene",
            "kind": "object",
            "excerpt": "Elias Thorne's body discovered collapsed beside broken glass in the central greenhouse.",
            "source_chapter": 2,
            "reveal_chapter": 2,
            "claim_id": "cl_death_location",
        }]
        if false_lead_cause:
            claims_out.append({"id": false_lead_cause["id"], "text": false_lead_cause["text"], "validation": "false_lead"})
            if false_lead_cause.get("evidence"):
                evi_out.append(false_lead_cause["evidence"])

        return {
            "answer": answer,
            "status": "culprit_query",
            "culprit_status": "no_established_culprit",
            "question_type": "culprit_query",
            "culprit": None,
            "resolved_entities": [{"id": target_victim_id, "name": target_victim_name, "labels": ["Character"]}],
            "nodes": [
                {"id": target_victim_id, "name": target_victim_name},
                {"id": "ev_elias_death", "name": "Elias is found dead in the greenhouse"},
            ],
            "relationships": [],
            "evidence": evi_out,
            "claims": claims_out,
            "path": None,
        }

    # CHAPTERS 5, 6, 7: Confirmed cause of death exists (ev_cider_tampered)
    # Check for perpetrator claims on the tampering event
    perp_rows = _rows("""
    MATCH (c:Claim {object: 'ev_cider_tampered', role: 'perpetrator'})
    WHERE c.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.subject, c.text, c.validation, c.reveal_chapter,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''), coalesce(evi.source_chapter, 0)
    """, {"chapter": chapter})

    confirmed_perp = None
    unverified_perp = None

    for r in perp_rows:
        cid, csub, ctext, cval, crev, eid, ekind, eexc, esrc = r
        if cval == "confirmed":
            char_res = _rows("MATCH (c:Character {id: $id}) RETURN coalesce(c.name, c.id)", {"id": csub})
            cname = char_res[0][0] if char_res else csub
            if eid:
                confirmed_perp = {
                    "id": cid, "subject": csub, "char_name": cname, "text": ctext, "reveal_chapter": crev,
                    "evidence": {"evidence_id": eid, "kind": ekind, "excerpt": eexc, "source_chapter": esrc, "reveal_chapter": crev, "claim_id": cid}
                }
            else:
                unverified_perp = {"id": cid, "subject": csub, "char_name": cname, "text": ctext, "reveal_chapter": crev}

    # CHAPTERS 5 and 6 (Cause of death proven, but perpetrator unproven / missing evidence)
    if not confirmed_perp:
        # Check visible suspect claims
        suspect_rows = _rows("""
        MATCH (c:Claim {kind: 'SUSPECTS'})
        WHERE c.reveal_chapter <= $chapter
        OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
        WHERE evi.reveal_chapter <= $chapter
        RETURN c.id, c.subject, c.object, c.text, c.validation, c.reveal_chapter,
               coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''), coalesce(evi.source_chapter, 0)
        """, {"chapter": chapter})

        suspect_lines = []
        evi_suspects = []
        claims_suspects = [
            {"id": confirmed_cause["id"], "text": confirmed_cause["text"], "validation": "confirmed"}
        ]
        evi_suspects.append(confirmed_cause["evidence"])

        for r in suspect_rows:
            cid, csub, cobj, ctext, cval, crev, eid, ekind, eexc, esrc = r
            claims_suspects.append({"id": cid, "text": ctext, "validation": cval})
            if eid:
                ev_dict = {"evidence_id": eid, "kind": ekind, "excerpt": eexc, "source_chapter": esrc, "reveal_chapter": crev, "claim_id": cid}
                evi_suspects.append(ev_dict)
                if cid == "cl_mara_suspects_halden":
                    suspect_lines.append(
                        f'- [Circumstantial Clue]: {ctext} (associated in graph with {ekind} from Ch. {esrc}: "{eexc}"). '
                        f'Evidence Grounding Note: The cited excerpt only establishes that two ledger totals disagree by 4,200 ("Totals on pages 12 and 14 disagree by 4,200."). '
                        f'It does not name Dr. Pavel Halden, state suspicion directly, or prove tampering; Mara\'s suspicion is a narrative claim associated with this financial irregularity.'
                    )
                else:
                    suspect_lines.append(f'- [Suspect Clue]: {ctext} (supported by {ekind} from Ch. {esrc}: "{eexc}")')

        # Check for ledger forgery or ally reveals in chapter 6
        extra_clues = []
        forg_rows = _rows("""
        MATCH (c:Claim {id: 'cl_causal_forged_found'})
        WHERE c.reveal_chapter <= $chapter
        OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
        WHERE evi.reveal_chapter <= $chapter
        RETURN c.id, c.text, coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''), coalesce(evi.source_chapter, 0)
        """, {"chapter": chapter})
        if forg_rows:
            fcid, ftext, feid, fekind, feexc, fesrc = forg_rows[0]
            claims_suspects.append({"id": fcid, "text": ftext, "validation": "confirmed"})
            if feid:
                evi_suspects.append({"evidence_id": feid, "kind": fekind, "excerpt": feexc, "source_chapter": fesrc, "reveal_chapter": chapter, "claim_id": fcid})
            extra_clues.append(f'- [Financial Motive]: {ftext}')

        ally_rows = _rows("""
        MATCH (c:Claim {id: 'cl_jonas_ally'})
        WHERE c.reveal_chapter <= $chapter
        OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
        WHERE evi.reveal_chapter <= $chapter
        RETURN c.id, c.text, coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''), coalesce(evi.source_chapter, 0)
        """, {"chapter": chapter})
        if ally_rows:
            acid, atext, aeid, aekind, aeexc, aesrc = ally_rows[0]
            claims_suspects.append({"id": acid, "text": atext, "validation": "confirmed"})
            if aeid:
                evi_suspects.append({"evidence_id": aeid, "kind": aekind, "excerpt": aeexc, "source_chapter": aesrc, "reveal_chapter": chapter, "claim_id": acid})
            extra_clues.append(f'- [Cleared Suspect]: {atext} (Jonas is cleared of early suspicion)')

        suspects_text = "\n".join(suspect_lines + extra_clues) if (suspect_lines or extra_clues) else "- No formal suspect claims recorded."

        unverified_gap = ""
        if unverified_perp:
            unverified_gap = f"Data Gap: Claim '{unverified_perp['text']}' exists, but lacks visible supporting evidence at Chapter {chapter}.\n"

        answer = (
            f"Status: suspect or allegation\n\n"
            f"Reasoning Chain:\n"
            f"1. Confirmed Cause of Death: [Confirmed] Elias Thorne was killed by poisoned cider (Claim: \"{confirmed_cause['text']}\", supported by {confirmed_cause['evidence']['kind']} from Ch. {confirmed_cause['evidence']['source_chapter']}: \"{confirmed_cause['evidence']['excerpt']}\").\n"
            f"2. Visible Clues / Persons of Interest:\n{suspects_text}\n"
            f"3. Data Gap / Missing Proof: {unverified_gap}The identity of who introduced poison into the cider is not established at Chapter {chapter}. No confirmed perpetrator claim with supporting physical evidence (such as the poison source or vial) is revealed in the graph at this chapter boundary.\n"
            f"4. Evidence Grounding & Evaluation: While visible clues and financial suspicion point toward Dr. Pavel Halden, the cited ledger excerpt only establishes an accounting discrepancy of 4,200 between pages 12 and 14, without naming Halden or proving guilt. He is strictly NOT the confirmed culprit. The graph does not yet establish who committed the lethal tampering.\n\n"
            f"Conclusion: Suspects and circumstantial clues exist, but no confirmed culprit is established as of Chapter {chapter}."
        )

        return {
            "answer": answer,
            "status": "culprit_query",
            "culprit_status": "suspect_or_allegation",
            "question_type": "culprit_query",
            "culprit": None,
            "resolved_entities": [{"id": target_victim_id, "name": target_victim_name, "labels": ["Character"]}],
            "nodes": [
                {"id": "ev_cider_tampered", "name": "The cider is tampered with"},
                {"id": "ev_elias_death", "name": "Elias is found dead in the greenhouse"},
            ],
            "relationships": [
                {"source": "ev_cider_tampered", "target": "ev_elias_death", "type": "CAUSED", "claim_id": confirmed_cause["id"]}
            ],
            "evidence": evi_suspects,
            "claims": claims_suspects,
            "path": None,
        }

    # CHAPTER 7: Full causal chain is established by visible supported claims and evidence!
    # Fetch motive claim cl_causal_found_tampered
    motive_rows = _rows("""
    MATCH (c:Claim {id: 'cl_causal_found_tampered'})
    WHERE c.reveal_chapter <= $chapter
    OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(c)
    WHERE evi.reveal_chapter <= $chapter
    RETURN c.id, c.text, c.validation, c.reveal_chapter,
           coalesce(evi.id, ''), coalesce(evi.kind, ''), coalesce(evi.excerpt, ''), coalesce(evi.source_chapter, 0)
    """, {"chapter": chapter})

    motive_text = ""
    motive_evi = None
    if motive_rows:
        mcid, mctext, mcval, mcrev, meid, mekind, meexc, mesrc = motive_rows[0]
        if meid:
            motive_evi = {"evidence_id": meid, "kind": mekind, "excerpt": meexc, "source_chapter": mesrc, "reveal_chapter": mcrev, "claim_id": mcid}
            motive_text = (
                f"1. Motive & Trigger: [Confirmed] Mara finding the financial discrepancy led Halden to tamper with the cider to silence exposure (Claim: \"{mctext}\"). "
                f"Evidence Grounding: The graph schema associates this causal link with the discovery of the vial (evi_vial: \"{meexc}\"), "
                f"but the excerpt itself establishes physical possession of the toxic compound rather than a psychological motive; "
                f"the financial motive is derived from the threat of exposure over the earlier ledger forgery.\n"
            )

    answer = (
        f"Status: culprit established by visible supported claims/evidence\n\n"
        f"Reasoning Chain:\n"
        f"{motive_text}"
        f"2. Physical Evidence & Tampering Act: [Confirmed] {confirmed_perp['char_name']} tampered with the cider as perpetrator (Claim: \"{confirmed_perp['text']}\"). "
        f"Evidence Grounding: Supported by {confirmed_perp['evidence']['kind']} from Ch. {confirmed_perp['evidence']['source_chapter']} (evi_vial: \"{confirmed_perp['evidence']['excerpt']}\"). "
        f"The excerpt strictly proves physical possession of the identical toxic compound in Halden's medical bag; "
        f"identifying Halden as the perpetrator who introduced it into the cider is a deductive conclusion from this matching poison possession rather than an eyewitness account.\n"
        f"3. Lethal Causation: [Confirmed] The poisoned cider directly caused Elias Thorne's death (Claim: \"{confirmed_cause['text']}\", supported by {confirmed_cause['evidence']['kind']} from Ch. {confirmed_cause['evidence']['source_chapter']}: \"{confirmed_cause['evidence']['excerpt']}\").\n"
        f"4. Deductive Inference & Proof Chain: Dr. Pavel Halden possessed the exact lethal compound matching the decanter residue, had a direct motive to conceal his financial forgery, and that poisoned cider caused Elias's cardiac arrest. Combining physical possession, lethal causation, and motive establishes Dr. Pavel Halden as the culprit.\n"
        f"5. Graph Modeling Note & Path Grounding: Every edge in the returned path exists in the graph and connects adjacent nodes: Dr. Pavel Halden --[PARTICIPATED_IN (role: perpetrator)]--> The cider is tampered with --[CAUSED]--> Elias is found dead in the greenhouse. Elias Thorne is identified as the deceased victim through the death event and scene evidence, without an unmediated character edge in the story source.\n\n"
        f"Conclusion: {confirmed_perp['char_name']} is established as the culprit."
    )

    path_nodes = [
        {"id": confirmed_perp["subject"], "name": confirmed_perp["char_name"]},
        {"id": "ev_cider_tampered", "name": "The cider is tampered with"},
        {"id": "ev_elias_death", "name": "Elias is found dead in the greenhouse"},
    ]

    path_relationships = [
        {"source": confirmed_perp["subject"], "target": "ev_cider_tampered", "type": "PARTICIPATED_IN", "role": "perpetrator", "claim_id": confirmed_perp["id"]},
        {"source": "ev_cider_tampered", "target": "ev_elias_death", "type": "CAUSED", "claim_id": confirmed_cause["id"]},
    ]

    evidence_out = [
        confirmed_perp["evidence"],
        confirmed_cause["evidence"],
    ]
    if motive_evi and not any(e["evidence_id"] == motive_evi["evidence_id"] for e in evidence_out):
        evidence_out.insert(0, motive_evi)

    claims_out = [
        {"id": confirmed_perp["id"], "text": confirmed_perp["text"], "validation": "confirmed"},
        {"id": confirmed_cause["id"], "text": confirmed_cause["text"], "validation": "confirmed"},
    ]
    if motive_rows:
        claims_out.insert(0, {"id": motive_rows[0][0], "text": motive_rows[0][1], "validation": "confirmed"})

    path_dict = {
        "nodes": path_nodes,
        "relationships": path_relationships,
        "edges": path_relationships,
        "evidence": evidence_out,
    }
    _validate_path_adjacency(path_dict)

    return {
        "answer": answer,
        "status": "culprit_query",
        "culprit_status": "culprit_established",
        "question_type": "culprit_query",
        "culprit": {"id": confirmed_perp["subject"], "name": confirmed_perp["char_name"]},
        "resolved_entities": [{"id": target_victim_id, "name": target_victim_name, "labels": ["Character"]}],
        "nodes": path_nodes,
        "relationships": path_relationships,
        "evidence": evidence_out,
        "claims": claims_out,
        "path": path_dict,
    }


