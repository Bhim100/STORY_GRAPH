# How StoryGraph Follows the Clues

StoryGraph uses FalkorDB to turn story details into a connected map. This guide explains what the main query patterns are meant to do and some of the problems we had to solve while building them.

The Cypher snippets below are examples of the ideas behind the queries. Property names and graph patterns should match the current StoryGraph schema before using them directly.

## Graph algorithms and techniques we use

StoryGraph combines graph traversal with Cypher filters. The names can sound intimidating, but each technique answers a practical question:

- **Shortest-path search:** Finds a small chain of connections between two entities, such as a character and an event. We limit the path length so the result stays understandable. In an unweighted graph, shortest-path search is commonly performed with a breadth-first search (BFS).
- **Chapter-filtered traversal:** Follows only nodes and relationships revealed by the selected chapter. This is how the graph avoids showing later information while the reader explores earlier chapters.
- **Neighborhood expansion (an event’s local network):** Starts from one event and gathers its nearby characters, location, and evidence. This is useful for questions like “Who was involved, and where did it happen?”
- **Evidence-aware matching:** Uses Cypher pattern matching to retrieve claims with their supporting evidence. This makes it possible for the interface to show the source behind a connection.
- **Time-aware claim status:** Uses conditional logic to decide whether an earlier claim has been superseded by a later revelation at the reader’s current chapter.

These techniques do different jobs: path search finds a route, chapter filters decide what is currently visible, and evidence matching helps readers inspect why a relationship appears. A path is not proof by itself; its relationships and source passages still need to support the answer.

## 1. Keeping later chapters hidden

### The challenge

A reader may be exploring Chapter 2 while the graph already contains facts from Chapter 8. Showing those facts too early would spoil the story.

### How we addressed it

We use a chapter boundary when retrieving graph data. Entities, relationships, and supporting evidence are included only when their reveal chapter is at or before the selected boundary.

```cypher
MATCH (source)-[r]->(target)
WHERE r.reveal_chapter <= $boundary_chapter
  AND source.reveal_chapter <= $boundary_chapter
  AND target.reveal_chapter <= $boundary_chapter
RETURN source.name AS source,
       type(r) AS relationship,
       target.name AS target
```

This depends on chapter metadata being correct. If a fact is assigned the wrong reveal chapter, the filter cannot fix that mistake by itself.

## 2. Showing the evidence behind a connection

### The challenge

A graph connection is only useful if readers can understand where it came from. We also needed to avoid presenting a model-generated relationship as a fact without source support.

### How we addressed it

Claims can be linked to evidence excerpts. The query retrieves claims and the available evidence so the interface can show the supporting passage and its chapter.

```cypher
MATCH (claim:Claim {id: $claim_id})
OPTIONAL MATCH (evidence:Evidence)-[:SUPPORTS]->(claim)
WHERE claim.reveal_chapter <= $boundary_chapter
  AND evidence.reveal_chapter <= $boundary_chapter
RETURN claim.text AS claim,
       claim.kind AS relationship,
       claim.validation AS status,
       collect(DISTINCT evidence.excerpt) AS evidence
```

The importer should also check that an excerpt appears in the source manuscript before accepting it. A valid-looking graph query cannot prove that an excerpt is accurate; that check belongs in the extraction and validation code.

## 3. Connecting two story elements

### The challenge

Two characters may never meet directly but still be connected through a place, group, event, or another character. A simple search for both names does not explain that chain.

### How we addressed it

We look for a short path through the graph, then return the entities and relationships along that path.

```cypher
MATCH (a {id: $entity_a}), (b {id: $entity_b})
MATCH path = shortestPath((a)-[*..4]-(b))
WHERE ALL(node IN nodes(path)
          WHERE node.reveal_chapter <= $boundary_chapter)
  AND ALL(rel IN relationships(path)
          WHERE rel.reveal_chapter <= $boundary_chapter)
RETURN [node IN nodes(path) |
        coalesce(node.name, node.title)] AS entities,
       [rel IN relationships(path) | type(rel)] AS connections
```

The result is a possible graph path, not proof that the characters are allies or share a motive. Each step should be shown with its relationship label and, where available, its evidence.

## 4. Preserving earlier theories

### The challenge

Mystery stories change what the reader knows. A suspect may look guilty early on, then later evidence may undermine that theory. Deleting the earlier claim would hide how the investigation changed.

### How we addressed it

Instead of deleting an earlier claim, we can retain it and link it to a later claim that supersedes it. A chapter-aware query can show whether the replacement has been revealed yet.

```cypher
MATCH (claim:Claim {id: $claim_id})
WHERE claim.reveal_chapter <= $boundary_chapter
OPTIONAL MATCH (replacement:Claim {id: claim.superseded_by})
RETURN claim.text AS statement,
       CASE
         WHEN replacement IS NOT NULL
          AND replacement.reveal_chapter <= $boundary_chapter
         THEN 'superseded'
         ELSE 'current'
       END AS status
```

This lets the investigation’s history remain visible while respecting the reader’s current chapter.

## 5. Exploring an event

### The challenge

Readers often ask what happened at a particular scene: who was involved, where it took place, and what evidence was found. Keeping an event’s location only as plain text made it harder to explore the scene in the graph.

### How we addressed it

Events can be connected to participating characters and locations. If the source supports a location for an event, the graph can store that as an `OCCURS_AT` relationship.

```cypher
MATCH (event:Event {id: $event_id})
WHERE event.reveal_chapter <= $boundary_chapter
OPTIONAL MATCH (character:Character)-[participation:PARTICIPATED_IN]->(event)
WHERE participation.reveal_chapter <= $boundary_chapter
OPTIONAL MATCH (event)-[occurs:OCCURS_AT]->(location:Location)
WHERE occurs.reveal_chapter <= $boundary_chapter
RETURN event.title AS event,
       location.name AS location,
       collect(DISTINCT {
         name: character.name,
         role: participation.role
       }) AS participants
```

During development, we also found that locations could be extracted without becoming connected to anything. We improved event-to-location linking so those places could be explored. The link still needs to be supported by the story text; automatically attaching every unused location to an event would make the graph look complete but could introduce false information.

## 6. Finding what is known about a suspect

A question such as “Why was this person suspected?” needs more than a path between two names. StoryGraph needs to retrieve claims about suspicion, relevant events, and their evidence, while keeping “suspected” distinct from “confirmed.”

A simplified query might look like this:

```cypher
MATCH (person:Character)-[relationship]->(event:Event {id: $event_id})
WHERE relationship.reveal_chapter <= $boundary_chapter
OPTIONAL MATCH (evidence:Evidence)-[:SUPPORTS]->(claim:Claim)
WHERE claim.id = relationship.claim_id
  AND evidence.reveal_chapter <= $boundary_chapter
RETURN person.name AS person,
       type(relationship) AS connection,
       collect(DISTINCT evidence.excerpt) AS evidence
```

The answer should describe a suspicion as a suspicion. A graph connection alone does not establish that someone committed a crime.

# Problems we encountered while building the graph

## Separating people who share a surname

In *The Adventure of the Cardboard Box*, the Cushing sisters share a surname and are sometimes referred to by titles such as “Miss Cushing.” A loose surname-based matcher risked merging different sisters into one character.

We added checks that consider given names and known aliases before merging entities. The goal is to combine references that the story identifies as the same person while keeping Susan, Sarah, and Mary separate.

## Following one person across changing names

A character may be introduced by a maiden name and later referred to by a married name or title. If those references are stored as separate people, their evidence and relationships become split across multiple dossiers.

We improved alias matching to compare new names against existing canonical names and aliases. Marriage-related name variants should only be combined when the story supports that identity. This needs careful review because name changes and titles can be ambiguous.

## Connecting locations without guessing

Some extracted locations appeared in the graph but had no relationships. We found that location names were sometimes stored as event text without a graph connection.

We added support for linking an event to its location when the manuscript provides evidence for that link. This makes locations more useful in the graph while avoiding arbitrary connections made just to eliminate isolated nodes.

## Routing “ask about this entity” questions correctly

A question like “How is Tobias Quill connected to the story?” names one entity, but a broad connection detector initially treated “the story” as if it were a second entity.

We adjusted the routing order so single-entity profile questions are recognized before two-entity connection questions. We also added handling for phrases such as “connected to the story” so they open the entity’s profile rather than asking the user to name another character.

## Showing how an investigation changes

Early suspicions and later revelations both matter to a mystery. Removing an old theory when new information appears would erase the reader’s path through the investigation.

We designed claim history so a later revelation can supersede an earlier claim. The chapter boundary determines when the reader sees that change.

# What these queries can and cannot tell us

Cypher helps StoryGraph retrieve and connect information that is already represented in the graph. It does not guarantee that the book was extracted perfectly, that every relationship is present, or that a shortest path is meaningful by itself.

For that reason, StoryGraph should show the path, its relationship labels, the relevant chapter, and available evidence. Readers can then see how the answer was assembled and where the graph may still have gaps.
