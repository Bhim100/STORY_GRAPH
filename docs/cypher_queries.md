# StoryGraph Cypher Queries Reference

## Boundary-Filtered Traversal & Discovery Queries

### 1. Retrieve Visible Entities at Chapter Boundary $N$
```cypher
MATCH (n)
WHERE (n:Character OR n:Location OR n:Faction OR n:Event)
  AND n.reveal_chapter <= $boundary_chapter
RETURN n.id AS id, labels(n)[0] AS label, coalesce(n.name, n.title) AS title, n.reveal_chapter AS reveal_chapter
ORDER BY n.reveal_chapter ASC
```

### 2. Retrieve Traversable Supported Edges at Boundary $N$
Retrieves edges where endpoints, edge, and at least one supporting evidence are all revealed by chapter $N$:
```cypher
MATCH (source)-[r]->(target)
WHERE r.reveal_chapter <= $boundary_chapter
  AND source.reveal_chapter <= $boundary_chapter
  AND target.reveal_chapter <= $boundary_chapter
  AND EXISTS {
    MATCH (evi:Evidence)-[:SUPPORTS]->(cl:Claim {id: r.claim_id})
    WHERE evi.reveal_chapter <= $boundary_chapter
  }
RETURN source.id AS source, type(r) AS relationship, target.id AS target, r.claim_id AS claim_id
```

### 3. Ambiguous Entity Lookup by Name or Alias at Boundary $N$
Matches by name or aliases, respecting boundary filtering:
```cypher
MATCH (c:Character)
WHERE c.reveal_chapter <= $boundary_chapter
  AND (c.name CONTAINS $query OR $query IN c.aliases)
RETURN c.id AS id, c.name AS name, c.role AS role, c.aliases AS aliases
```

### 4. Fetch Claim Details with Dynamic Status Computation
```cypher
MATCH (cl:Claim {id: $claim_id})
WHERE cl.reveal_chapter <= $boundary_chapter
OPTIONAL MATCH (evi:Evidence)-[:SUPPORTS]->(cl)
WHERE evi.reveal_chapter <= $boundary_chapter
OPTIONAL MATCH (replacement:Claim {id: cl.superseded_by})
RETURN cl.id AS id,
       cl.text AS text,
       cl.kind AS kind,
       cl.validation AS validation,
       collect(DISTINCT evi.id) AS visible_evidence_ids,
       CASE
         WHEN replacement IS NOT NULL AND replacement.reveal_chapter <= $boundary_chapter THEN 'superseded'
         ELSE 'current'
       END AS status,
       CASE
         WHEN replacement IS NOT NULL AND replacement.reveal_chapter <= $boundary_chapter THEN replacement.id
         ELSE NULL
       END AS superseded_by
```

### 5. Multi-Hop Causal Chain Query (e.g. Ledger Forgery to Death)
```cypher
MATCH path = (e1:Event)-[:CAUSED*1..5]->(e2:Event)
WHERE ALL(r IN relationships(path) WHERE r.reveal_chapter <= $boundary_chapter)
  AND ALL(n IN nodes(path) WHERE n.reveal_chapter <= $boundary_chapter)
RETURN [n IN nodes(path) | n.title] AS event_titles
```
