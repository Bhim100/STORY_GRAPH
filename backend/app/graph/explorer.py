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

    # Check common entity aliases
    name_lower = cleaned_name.lower()
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


def get_event_evidence_query(question: str, resolved_entities: List[Dict[str, Any]], chapter: int) -> Dict[str, Any]:
    """Unified dispatcher executing controlled parameterized Cypher query templates for event and evidence queries."""
    q_lower = question.lower()

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

    # 2. Suspect / Allegation Queries (e.g. "Why was Jonas suspected?")
    if any(w in q_lower for w in ["suspect", "allegation", "accuse", "antagonist", "quarrel", "threat"]):
        char_entity = next((e for e in resolved_entities if "Character" in e.get("labels", []) or e.get("id", "").startswith("c_")), None)
        if char_entity:
            return get_suspect_allegations(char_entity["id"], chapter)

    # 3. Implicating / Evidence Connecting Queries (e.g. "What evidence connects Halden to the death?", "What evidence implicates Halden?")
    if any(w in q_lower for w in ["evidence", "connect", "implicate", "against", "tie", "involve"]):
        char_entity = next((e for e in resolved_entities if "Character" in e.get("labels", []) or e.get("id", "").startswith("c_")), None)
        event_entity = next((e for e in resolved_entities if "Event" in e.get("labels", []) or e.get("id", "").startswith("ev_")), None)
        if char_entity:
            event_id = event_entity["id"] if event_entity else None
            return get_implicating_evidence(char_entity["id"], event_id, chapter)

    # 4. General Event Queries (e.g. "What happened at the harvest dinner?")
    event_entity = next((e for e in resolved_entities if "Event" in e.get("labels", []) or e.get("id", "").startswith("ev_")), None)
    if event_entity:
        return get_general_event_query(event_entity["id"], chapter)

    # 5. Fallback if no matching events/evidence established
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

