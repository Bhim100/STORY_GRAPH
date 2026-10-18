"""StoryGraph AI Agent for spoiler-aware narrative question answering."""
from typing import Any, Dict
from app.graph.explorer import find_connection, get_entity_profile, get_collection_query, get_event_evidence_query
from app.llm.interpreter import interpret_question
from app.llm.generator import generate_grounded_answer
from app.llm.router import route_question, QuestionType


def answer_question(question: str, chapter: int) -> Dict[str, Any]:
    """Orchestrates deterministic question routing and response generation:

    1. Accepts question & reader chapter.
    2. Validates chapter boundary (>= 1).
    3. Routes question deterministically into:
       - connection between two entities
       - profile of one entity
       - collection/list query
       - event or evidence query
       - culprit or 'who did it?' query
       - unsupported / unrelated query
    4. Handles entity ambiguity and spoiler boundary rules.
    5. Dispatches to appropriate handler (preserving existing connection pathfinder).
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

    try:
        # Step 1: Deterministic Question Routing & Boundary Entity Resolution
        route = route_question(question, chapter)

        # Ambiguous entity handling: prompt clarification with options
        if route.get("status") == "clarification_needed":
            return {
                "answer": route.get("answer", "Clarification needed to proceed."),
                "status": "clarification_needed",
                "question_type": route.get("question_type"),
                "resolved_entities": route.get("resolved_entities", []),
                "entities": route.get("resolved_entities", []),
                "ambiguous_options": route.get("ambiguous_options", []),
                "nodes": [],
                "relationships": [],
                "evidence": [],
                "path": None,
            }

        # Unresolved / hidden entity handling (zero spoiler leakage)
        if route.get("status") == "unresolved_entity":
            return {
                "answer": route.get("answer", "Entity not identified."),
                "status": "unresolved_entity",
                "question_type": route.get("question_type"),
                "resolved_entities": [],
                "entities": route.get("resolved_entities", []),
                "nodes": [],
                "relationships": [],
                "evidence": [],
                "path": None,
            }

        # Unsupported / unrelated questions: reject without hallucinating
        if route.get("question_type") == QuestionType.UNSUPPORTED or route.get("status") == "unsupported":
            return {
                "answer": route.get("answer", "I cannot answer this question from the supported graph operations."),
                "status": "unsupported_question",
                "question_type": QuestionType.UNSUPPORTED,
                "resolved_entities": [],
                "nodes": [],
                "relationships": [],
                "evidence": [],
                "path": None,
            }

        # Entity Profile Handler
        if route.get("question_type") == QuestionType.ENTITY_PROFILE:
            resolved = route.get("resolved_entities", [])
            entity = resolved[0] if resolved else None
            if not entity:
                return {
                    "answer": "Could not identify which entity to profile.",
                    "status": "clarification_needed",
                    "question_type": QuestionType.ENTITY_PROFILE,
                    "resolved_entities": [],
                    "nodes": [],
                    "relationships": [],
                    "evidence": [],
                    "path": None,
                }
            profile = get_entity_profile(entity["id"], chapter)
            if not profile:
                return {
                    "answer": f"Entity '{entity['name']}' is not revealed or does not exist at Chapter {chapter}.",
                    "status": "unresolved_entity",
                    "question_type": QuestionType.ENTITY_PROFILE,
                    "resolved_entities": [],
                    "nodes": [],
                    "relationships": [],
                    "evidence": [],
                    "path": None,
                }
            node_data = profile["node"]
            return {
                "answer": profile["answer"],
                "status": "entity_profile",
                "question_type": QuestionType.ENTITY_PROFILE,
                "resolved_entities": [node_data],
                "nodes": [node_data],
                "relationships": profile.get("connections", []),
                "evidence": profile.get("evidence", []),
                "profile": profile,
                "path": None,
            }

        # Collection / List Query Handler
        if route.get("question_type") == QuestionType.COLLECTION_QUERY:
            resolved = route.get("resolved_entities", [])
            target_entity = resolved[0] if resolved else None
            target_id = target_entity["id"] if target_entity else None
            collection_res = get_collection_query(target_id, question, chapter)
            return {
                "answer": collection_res["answer"],
                "status": collection_res.get("status", "collection_query"),
                "question_type": QuestionType.COLLECTION_QUERY,
                "resolved_entities": resolved,
                "nodes": collection_res.get("nodes", []),
                "relationships": collection_res.get("relationships", []),
                "evidence": collection_res.get("evidence", []),
                "members": collection_res.get("members", []),
                "path": None,
            }

        # Event / Evidence Query Handler
        if route.get("question_type") == QuestionType.EVENT_EVIDENCE:
            resolved = route.get("resolved_entities", [])
            ev_res = get_event_evidence_query(question, resolved, chapter)
            return {
                "answer": ev_res["answer"],
                "status": ev_res.get("status", "event_evidence"),
                "question_type": QuestionType.EVENT_EVIDENCE,
                "resolved_entities": resolved,
                "nodes": ev_res.get("nodes", []),
                "relationships": ev_res.get("relationships", []),
                "evidence": ev_res.get("evidence", []),
                "events": ev_res.get("events", []),
                "claims": ev_res.get("claims", []),
                "path": None,
            }

        # Culprit / Who Did It Query Handler
        if route.get("question_type") == QuestionType.CULPRIT_QUERY:
            return {
                "answer": (
                    f"This question was routed to the culprit/who-did-it query handler "
                    f"(handler is not implemented until Phase 2). "
                    f"The culprit is not established by available graph data at Chapter {chapter}."
                ),
                "status": "culprit_query",
                "question_type": QuestionType.CULPRIT_QUERY,
                "resolved_entities": route.get("resolved_entities", []),
                "nodes": route.get("resolved_entities", []),
                "relationships": [],
                "evidence": [],
                "path": None,
            }

        # Two-Entity Connection Handler (Preserve existing connection route)
        interpretation = interpret_question(question, chapter)
        status = interpretation.get("status")

        if status in ("clarification_needed", "unresolved_entity"):
            return {
                "answer": interpretation.get("answer", "Clarification needed to proceed."),
                "status": status,
                "question_type": QuestionType.CONNECTION,
                "resolved_entities": interpretation.get("resolved_entities", []),
                "entities": interpretation.get("entities", []),
                "ambiguous_options": interpretation.get("ambiguous_options", []),
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
                "question_type": QuestionType.CONNECTION,
                "resolved_entities": resolved,
                "entities": interpretation.get("entities", []),
                "nodes": [],
                "relationships": [],
                "evidence": [],
                "path": None,
            }

        entity_a, entity_b = resolved[0], resolved[1]

        # Controlled FalkorDB path search and evidence retrieval
        path = find_connection(entity_a["id"], entity_b["id"], chapter)
        if not path or not path.get("nodes"):
            return {
                "answer": (
                    f"The available story graph does not establish a supported connection "
                    f"between {entity_a['name']} and {entity_b['name']} at Chapter {chapter}."
                ),
                "status": "no_path",
                "question_type": QuestionType.CONNECTION,
                "resolved_entities": [entity_a, entity_b],
                "nodes": [],
                "relationships": [],
                "evidence": [],
                "path": None,
            }

        # Grounded explanation generation
        answer_text = generate_grounded_answer(question, path, chapter)

        return {
            "answer": answer_text,
            "status": "answered",
            "question_type": QuestionType.CONNECTION,
            "resolved_entities": [entity_a, entity_b],
            "nodes": path.get("nodes", []),
            "relationships": path.get("relationships", []),
            "evidence": path.get("evidence", []),
            "path": path,
        }
    except Exception:
        return {
            "answer": "Unable to complete investigation due to a temporary service error. Please try again shortly.",
            "status": "error",
            "resolved_entities": [],
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "path": None,
        }
