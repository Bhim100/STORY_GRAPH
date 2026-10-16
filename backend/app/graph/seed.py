"""Seed JSON mystery stories into FalkorDB with schema validation and spoiler boundaries."""
import json
from pathlib import Path
from typing import Optional, Dict, Any, Set
from app.db import get_graph
from app.models import StoryDataset


def load_story_dataset(file_path: Path) -> StoryDataset:
    """Loads and validates story data using Pydantic model."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return StoryDataset.model_validate(data)


def validate_story_integrity(story: StoryDataset) -> None:
    """Validates referential integrity and schema consistency for a story."""
    # Collect all valid entity IDs
    entity_ids: Set[str] = set()
    for c in story.characters:
        entity_ids.add(c.id)
    for l in story.locations:
        entity_ids.add(l.id)
    for f in story.factions:
        entity_ids.add(f.id)
    for ev in story.events:
        entity_ids.add(ev.id)

    claim_map: Dict[str, Any] = {cl.id: cl for cl in story.claims}

    # Validate claims
    for cl in story.claims:
        if cl.subject not in entity_ids:
            raise ValueError(f"Claim {cl.id}: Subject '{cl.subject}' does not exist among entities.")
        if cl.object not in entity_ids:
            raise ValueError(f"Claim {cl.id}: Object '{cl.object}' does not exist among entities.")
        if cl.superseded_by and cl.superseded_by not in claim_map:
            raise ValueError(f"Claim {cl.id}: Superseded claim '{cl.superseded_by}' not found.")

    # Validate evidence
    for evi in story.evidence:
        for claim_id in evi.supports:
            if claim_id not in claim_map:
                raise ValueError(f"Evidence {evi.id}: Supported claim '{claim_id}' not found.")


def seed_story_to_falkordb(story: StoryDataset, graph_name: Optional[str] = None) -> None:
    """Seeds validated story entities, claims, evidence, and traversable edges into FalkorDB."""
    validate_story_integrity(story)
    graph = get_graph(graph_name or story.story_id)

    # Clean existing graph before re-seeding
    try:
        graph.delete()
    except Exception:
        pass

    # 1. Seed Story Root Node
    graph.query(
        "CREATE (:Story {id: $id, title: $title, description: $description})",
        {"id": story.story_id, "title": story.title, "description": story.description}
    )

    # 2. Seed Characters
    for c in story.characters:
        graph.query(
            """
            CREATE (:Character {
                id: $id,
                story_id: $story_id,
                name: $name,
                aliases: $aliases,
                role: $role,
                reveal_chapter: $reveal_chapter
            })
            """,
            {
                "id": c.id,
                "story_id": c.story_id,
                "name": c.name,
                "aliases": c.aliases,
                "role": c.role,
                "reveal_chapter": c.reveal_chapter
            }
        )

    # 3. Seed Locations
    for loc in story.locations:
        graph.query(
            """
            CREATE (:Location {
                id: $id,
                story_id: $story_id,
                name: $name,
                reveal_chapter: $reveal_chapter
            })
            """,
            {
                "id": loc.id,
                "story_id": loc.story_id,
                "name": loc.name,
                "reveal_chapter": loc.reveal_chapter
            }
        )

    # 4. Seed Factions
    for fac in story.factions:
        graph.query(
            """
            CREATE (:Faction {
                id: $id,
                story_id: $story_id,
                name: $name,
                reveal_chapter: $reveal_chapter
            })
            """,
            {
                "id": fac.id,
                "story_id": fac.story_id,
                "name": fac.name,
                "reveal_chapter": fac.reveal_chapter
            }
        )

    # 5. Seed Events
    for ev in story.events:
        graph.query(
            """
            CREATE (:Event {
                id: $id,
                story_id: $story_id,
                title: $title,
                event_chapter: $event_chapter,
                reveal_chapter: $reveal_chapter
            })
            """,
            {
                "id": ev.id,
                "story_id": ev.story_id,
                "title": ev.title,
                "event_chapter": ev.event_chapter,
                "reveal_chapter": ev.reveal_chapter
            }
        )

    # 6. Seed Claims
    for cl in story.claims:
        graph.query(
            """
            CREATE (:Claim {
                id: $id,
                story_id: $story_id,
                kind: $kind,
                subject: $subject,
                object: $object,
                role: $role,
                text: $text,
                reveal_chapter: $reveal_chapter,
                superseded_by: $superseded_by,
                validation: $validation
            })
            """,
            {
                "id": cl.id,
                "story_id": cl.story_id,
                "kind": cl.kind,
                "subject": cl.subject,
                "object": cl.object,
                "role": cl.role or "",
                "text": cl.text,
                "reveal_chapter": cl.reveal_chapter,
                "superseded_by": cl.superseded_by or "",
                "validation": cl.validation
            }
        )

        # Create traversable graph edge matching the claim
        # Relationship type is dynamic based on cl.kind
        edge_query = f"""
        MATCH (s {{id: $subject}}), (o {{id: $object}})
        CREATE (s)-[:{cl.kind} {{
            claim_id: $claim_id,
            story_id: $story_id,
            reveal_chapter: $reveal_chapter,
            role: $role
        }}]->(o)
        """
        graph.query(
            edge_query,
            {
                "subject": cl.subject,
                "object": cl.object,
                "claim_id": cl.id,
                "story_id": cl.story_id,
                "reveal_chapter": cl.reveal_chapter,
                "role": cl.role or ""
            }
        )

    # 7. Seed Evidence and SUPPORTS relationships
    for evi in story.evidence:
        graph.query(
            """
            CREATE (:Evidence {
                id: $id,
                story_id: $story_id,
                kind: $kind,
                excerpt: $excerpt,
                source_chapter: $source_chapter,
                reveal_chapter: $reveal_chapter
            })
            """,
            {
                "id": evi.id,
                "story_id": evi.story_id,
                "kind": evi.kind,
                "excerpt": evi.excerpt,
                "source_chapter": evi.source_chapter,
                "reveal_chapter": evi.reveal_chapter
            }
        )

        for claim_id in evi.supports:
            graph.query(
                """
                MATCH (e:Evidence {id: $evi_id}), (c:Claim {id: $claim_id})
                CREATE (e)-[:SUPPORTS {reveal_chapter: $reveal_chapter}]->(c)
                """,
                {
                    "evi_id": evi.id,
                    "claim_id": claim_id,
                    "reveal_chapter": evi.reveal_chapter
                }
            )
