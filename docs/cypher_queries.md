# StoryGraph Cypher Queries Reference

## Core Inspection Queries

### 1. Get All Unlocked Entities
```cypher
MATCH (n)
WHERE n.id IN $unlocked_ids
RETURN n.id AS id, labels(n)[0] AS type, n.name AS name, n.description AS description
```

### 2. Discover Connected Clues and Characters
```cypher
MATCH (c:Character {id: $character_id})-[r]-(target)
WHERE target.id IN $unlocked_ids
RETURN type(r) AS relationship, target.id AS target_id, labels(target)[0] AS target_type, target.name AS target_name
```

### 3. Check Reveal Condition
```cypher
MATCH (clue:Clue {id: $clue_id})-[:REVEALS]->(secret:Secret {id: $secret_id})
RETURN secret
```
