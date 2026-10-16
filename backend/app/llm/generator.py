"""Grounded answer generation using only verified graph paths and visible evidence."""
import json
from typing import Any, Dict, List
from app.config import OPENAI_API_KEY, OPENAI_MODEL


def _format_deterministic_answer(path: Dict[str, Any], chapter: int) -> str:
    """Generates a concise, deterministic summary from verified path nodes, claims, and evidence."""
    nodes = path.get("nodes", [])
    relationships = path.get("relationships", [])
    evidence = path.get("evidence", [])

    if not nodes or not relationships:
        return f"A verified connection was found up to Chapter {chapter}, but details could not be formatted."

    # Build claim and evidence lookups
    claim_evidence_map: Dict[str, List[Dict[str, Any]]] = {}
    claim_text_map: Dict[str, str] = {}
    for item in evidence:
        cid = item.get("claim_id")
        if cid:
            claim_evidence_map.setdefault(cid, []).append(item)
            if "claim" in item:
                claim_text_map[cid] = item["claim"]

    # Assemble narrative sentence steps
    steps = []
    node_names = [n.get("name", n.get("id")) for n in nodes]
    overall_path_desc = " -> ".join(node_names)

    for rel in relationships:
        source_id = rel.get("source")
        target_id = rel.get("target")
        rel_type = rel.get("type", "RELATED_TO")
        claim_id = rel.get("claim_id")

        source_name = next((n.get("name") for n in nodes if n.get("id") == source_id), source_id)
        target_name = next((n.get("name") for n in nodes if n.get("id") == target_id), target_id)

        claim_text = claim_text_map.get(claim_id, f"{source_name} is connected to {target_name} ({rel_type})")
        ev_items = claim_evidence_map.get(claim_id, [])

        if ev_items:
            first_ev = ev_items[0]
            step_desc = f"{claim_text} (backed by {first_ev.get('kind', 'evidence')} from Chapter {first_ev.get('reveal_chapter')}: \"{first_ev.get('excerpt', '')}\")"
        else:
            step_desc = claim_text
        steps.append(step_desc)

    explanation = "; ".join(steps) + "."
    return f"As of Chapter {chapter}, {node_names[0]} connects to {node_names[-1]} via: {overall_path_desc}. Specifically, {explanation}"


def generate_grounded_answer(question: str, path: Dict[str, Any], chapter: int) -> str:
    """Generates an explanation using an LLM when configured, or a deterministic grounded summary."""
    if not path or not path.get("nodes"):
        return f"I can't establish a supported connection from information revealed by Chapter {chapter}."

    if not OPENAI_API_KEY:
        return _format_deterministic_answer(path, chapter)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        facts = [
            {
                "claim_id": e.get("claim_id"),
                "claim": e.get("claim"),
                "relationship": e.get("relationship"),
                "evidence_excerpt": e.get("excerpt"),
                "evidence_kind": e.get("kind"),
                "reveal_chapter": e.get("reveal_chapter"),
            }
            for e in path.get("evidence", [])
        ]

        payload = {
            "question": question,
            "chapter_boundary": chapter,
            "verified_path_nodes": [
                {"id": n.get("id"), "name": n.get("name"), "type": n.get("labels", [])}
                for n in path.get("nodes", [])
            ],
            "verified_path_edges": [
                {
                    "source": r.get("source"),
                    "target": r.get("target"),
                    "relationship": r.get("type"),
                    "claim_id": r.get("claim_id"),
                }
                for r in path.get("relationships", [])
            ],
            "visible_supporting_evidence": facts,
        }

        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are StoryGraph, a spoiler-safe mystery story assistant. "
                        "Explain ONLY the connection established by the provided verified graph path and visible evidence. "
                        "CRITICAL RULES:\n"
                        "1. Do NOT add plot details, characters, or theories not present in the verified data.\n"
                        "2. Do NOT reveal or hint at any events beyond the chapter boundary.\n"
                        "3. Explicitly cite the evidence supporting each relationship.\n"
                        "4. Keep the answer concise and direct."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        answer = completion.choices[0].message.content
        return answer.strip() if answer else _format_deterministic_answer(path, chapter)
    except Exception:
        # Graceful fallback on LLM error
        return _format_deterministic_answer(path, chapter)
