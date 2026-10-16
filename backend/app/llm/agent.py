"""StoryGraph AI Agent for spoiler-aware narrative question answering."""
from typing import Any, Dict
from app.graph.explorer import find_connection
from app.llm.interpreter import interpret_question
from app.llm.generator import generate_grounded_answer


def answer_question(question: str, chapter: int) -> Dict[str, Any]:
    """Orchestrates Phase 3 agent workflow:

    1. Accepts question & reader chapter.
    2. Interprets question & resolves entities against visible graph at chapter.
    3. Searches for shortest spoiler-safe, evidence-supported path in FalkorDB.
    4. Retrieves visible supporting evidence for all traversed claims.
    5. Generates concise grounded answer.
    6. Returns structured result with status, entities, path, and evidence.
    """
    if chapter < 1:
        return {
            "answer": "Chapter must be a positive integer (>= 1).",
            "status": "error",
            "resolved_entities": [],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "path": None,
        }

    # Step 1 & 2: Entity identification and spoiler-safe resolution
    interpretation = interpret_question(question, chapter)
    status = interpretation.get("status")

    if status in ("clarification_needed", "unresolved_entity"):
        return {
            "answer": interpretation.get("answer", "Clarification needed to proceed."),
            "status": status,
            "resolved_entities": interpretation.get("resolved_entities", []),
            "entities": interpretation.get("entities", []),
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "path": None,
        }

    resolved = interpretation.get("resolved_entities", [])
    if len(resolved) < 2:
        return {
            "answer": "Could not identify two distinct story entities to connect in this question.",
            "status": "clarification_needed",
            "resolved_entities": resolved,
            "entities": interpretation.get("entities", []),
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "path": None,
        }

    entity_a, entity_b = resolved[0], resolved[1]

    # Step 3 & 4: Controlled FalkorDB path search and evidence retrieval
    path = find_connection(entity_a["id"], entity_b["id"], chapter)
    if not path or not path.get("nodes"):
        return {
            "answer": (
                f"The available story graph does not establish a supported connection "
                f"between {entity_a['name']} and {entity_b['name']} at Chapter {chapter}."
            ),
            "status": "no_path",
            "resolved_entities": [entity_a, entity_b],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "path": None,
        }

    # Step 5 & 6: Grounded explanation generation
    answer_text = generate_grounded_answer(question, path, chapter)

    # Step 7: Structured result
    return {
        "answer": answer_text,
        "status": "answered",
        "resolved_entities": [entity_a, entity_b],
        "nodes": path.get("nodes", []),
        "relationships": path.get("relationships", []),
        "evidence": path.get("evidence", []),
        "path": path,
    }
