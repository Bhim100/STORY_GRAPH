# StoryGraph Graph Schema

## Core Conceptual Model
StoryGraph differentiates between three distinct ontological concepts:
1. **Event**: An objective occurrence in the story world (e.g., *Elias is poisoned at dinner*).
2. **Claim**: An assertion or relationship between entities (e.g., *“Halden perpetrated the poisoning”* or *“Mara is employed by Elias”*).
3. **Evidence**: An excerpted document, testimony, or physical object that supports a specific claim (e.g., *The vial found in Halden’s bag*).

> **Crucial Rule**: Evidence attaches to a specific **Claim**, never to an entire Character or Story.

---

## Node Labels & Key Properties

### 1. `:Character`
- `id` (string, unique, e.g., `c_elias_thorne`)
- `story_id` (string)
- `name` (string)
- `aliases` (list of strings, e.g., `["Halden", "Dr. Halden"]`)
- `role` (string)
- `reveal_chapter` (integer, when reader learns this character exists)

### 2. `:Location`
- `id` (string, unique, e.g., `l_greenhouse`)
- `story_id` (string)
- `name` (string)
- `reveal_chapter` (integer)

### 3. `:Faction`
- `id` (string, unique, e.g., `f_thorne_household`)
- `story_id` (string)
- `name` (string)
- `reveal_chapter` (integer)

### 4. `:Event`
- `id` (string, unique, e.g., `ev_cider_tampered`)
- `story_id` (string)
- `title` (string)
- `event_chapter` (integer, in-world chronological occurrence)
- `reveal_chapter` (integer, reader narrative disclosure)

### 5. `:Claim`
- `id` (string, unique, e.g., `cl_halden_perp`)
- `story_id` (string)
- `kind` (string, relationship type: `EMPLOYED_BY`, `KIN_OF`, `PHYSICIAN_OF`, `ALLY_OF`, `ANTAGONIST_OF`, `SUSPECTS`, `MEMBER_OF`, `PARTICIPATED_IN`, `OCCURRED_AT`, `CAUSED`)
- `subject` (string, entity ID)
- `object` (string, entity ID)
- `role` (string, optional: e.g. `perpetrator`, `victim`, `discoverer`)
- `text` (string, natural language claim statement)
- `reveal_chapter` (integer)
- `superseded_by` (string or empty, pointer to replacing claim ID)
- `validation` (string: `confirmed`, `alleged`, `false_lead`, `debunked`)

### 6. `:Evidence`
- `id` (string, unique, e.g., `evi_vial`)
- `story_id` (string)
- `kind` (`document` | `testimony` | `object`)
- `excerpt` (string, strictly restricted to facts known at its own `reveal_chapter`)
- `source_chapter` (integer)
- `reveal_chapter` (integer)

---

## Relationships & Graph Edges

| Relationship Type | Source → Target | Description | Properties |
| :--- | :--- | :--- | :--- |
| `EMPLOYED_BY`, `KIN_OF`, `PHYSICIAN_OF`, `ALLY_OF`, `ANTAGONIST_OF`, `SUSPECTS`, `MEMBER_OF` | Character → Character or Faction | Social, professional, or investigative ties | `claim_id`, `reveal_chapter`, `story_id` |
| `PARTICIPATED_IN` | Character → Event | Character involvement in an event | `role`, `claim_id`, `reveal_chapter`, `story_id` |
| `OCCURRED_AT` | Event → Location | Spatial anchoring of an event | `claim_id`, `reveal_chapter`, `story_id` |
| `CAUSED` | Event → Event | Causal chain link between events | `claim_id`, `reveal_chapter`, `story_id` |
| `SUPPORTS` | Evidence → Claim | Evidentiary grounding of an assertion | `reveal_chapter` |

---

## Design Invariants & Spoiler Boundary Rules

### 1. Dual Representation: Traversable Edge + Claim Node
Every traversable graph edge maps 1:1 to a `Claim` node bearing the identical `claim_id`.
- The **edge** is what path search algorithms traverse.
- The **Claim node** is what `Evidence` nodes attach to via `[:SUPPORTS]`.
- The edge mirrors `reveal_chapter` from its claim for maximum Cypher filter performance.

### 2. Traversal Usability at Boundary Chapter $N$
An edge is considered active and traversable at boundary chapter $N$ if and only if **all three** conditions hold:
1. Edge `reveal_chapter <= N`
2. Both endpoint nodes have `reveal_chapter <= N`
3. At least one `Evidence` supporting its matching claim has `reveal_chapter <= N`

A claim lacking visible evidence at chapter $N$ is classified as **unverified** and excluded from path traversals.

### 3. Dynamic Claim Status Computation
Claim status is **never** statically stored on the claim node as "superseded".
At boundary $N$, status is derived:
- If `superseded_by` is empty OR the replacing claim's `reveal_chapter > N`, the claim is **current**.
- If the replacing claim's `reveal_chapter <= N`, the claim is **superseded**.
- The `superseded_by` reference is strictly masked and never returned to the client prior to that replacing claim's reveal chapter.
