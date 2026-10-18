"""Grounded answer generation using only verified graph paths and visible evidence."""
import json
from typing import Any, Dict, List
from app.config import OPENAI_API_KEY, OPENAI_MODEL, get_llm_client


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


def validate_answer_grounding(answer: str, path: Dict[str, Any], chapter: int) -> bool:
    """Verifies that generated explanation does not introduce story characters or facts absent from the verified path."""
    if not answer or not answer.strip():
        return False

    # Extract allowed entity identifiers and names from verified path nodes
    allowed_names = set()
    for n in path.get("nodes", []):
        name = n.get("name")
        if name:
            allowed_names.add(name.lower())
            for part in name.split():
                if len(part) > 3:
                    allowed_names.add(part.lower())

    # Known story characters that, if mentioned without being in path, represent hallucinations or leaks
    known_story_names = [
        "elias thorne", "edith thorne", "mara voss", "ines calloway",
        "jonas reed", "pavel halden", "halden", "tobias quill", "ruth ames",
    ]

    ans_lower = answer.lower()
    for char_name in known_story_names:
        if char_name in ans_lower:
            # Must be in allowed names
            if not any(token in allowed_names for token in char_name.split() if len(token) > 3):
                return False

    return True


def generate_grounded_answer(question: str, path: Dict[str, Any], chapter: int) -> str:
    """Generates an explanation using an LLM when configured, or a deterministic grounded summary."""
    if not path or not path.get("nodes"):
        return f"I can't establish a supported connection from information revealed by Chapter {chapter}."

    client, model = get_llm_client()
    if not client:
        if OPENAI_API_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            model = OPENAI_MODEL
        else:
            return _format_deterministic_answer(path, chapter)

    try:
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
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are StoryGraph, a spoiler-safe mystery story assistant. "
                        "Explain ONLY the connection established by the provided verified graph path and visible evidence.\n\n"
                        "CRITICAL RULES:\n"
                        "1. Do NOT add plot details, characters, or theories not present in the verified data.\n"
                        "2. Do NOT reveal or hint at any events beyond the chapter boundary.\n"
                        "3. Explicitly cite the evidence supporting each relationship.\n"
                        "4. Keep the answer concise, direct, and well-grounded.\n\n"
                        "FORMATTING RULES:\n"
                        "- Organize your response with clear paragraph breaks (double newlines).\n"
                        "- When presenting intermediate steps or supporting evidence, use structured bullet points on their own separate lines:\n"
                        "  * **[Step or Role]:** [Description]\n"
                        "    > *Evidence:* \"[Supporting quote]\" (Ch. X)\n"
                        "- Never bunch multiple bullet points onto a single line."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        answer = completion.choices[0].message.content
        if answer and validate_answer_grounding(answer.strip(), path, chapter):
            return answer.strip()
        return _format_deterministic_answer(path, chapter)
    except Exception:
        # Graceful fallback on LLM error
        return _format_deterministic_answer(path, chapter)


def generate_grounded_profile_answer(profile_data: Dict[str, Any], question: str, chapter: int) -> str:
    """Generates an articulate investigator's profile summary using the LLM when available."""
    client, model = get_llm_client()
    default_ans = profile_data.get("answer", "")
    if not client:
        return default_ans

    try:
        node = profile_data.get("node", {})
        payload = {
            "entity": {
                "name": node.get("name"),
                "kind": node.get("kind"),
                "role": node.get("role"),
                "aliases": node.get("aliases", []),
                "first_revealed_chapter": node.get("reveal_chapter", 1),
            },
            "reader_current_chapter": chapter,
            "visible_relationships": profile_data.get("connections", []),
            "supporting_evidence": [
                {
                    "claim": ev.get("claim"),
                    "kind": ev.get("kind"),
                    "excerpt": ev.get("excerpt"),
                    "source_chapter": ev.get("source_chapter"),
                }
                for ev in profile_data.get("evidence", [])
            ],
            "question": question,
        }

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are StoryGraph, an intelligent, spoiler-safe mystery story assistant. "
                        "Synthesize an articulate, clear investigator's profile of this character/entity up to the reader's current chapter.\n\n"
                        "CRITICAL RULES:\n"
                        "1. Only use facts, connections, and evidence provided in the JSON data.\n"
                        "2. Do NOT invent or reveal any events beyond the reader's chapter.\n"
                        "3. Naturally weave in key supporting quotes and relationships in a structured, readable way.\n\n"
                        "FORMATTING RULES:\n"
                        "- Begin with a direct 1-2 sentence summary answering the question.\n"
                        "- Follow with a structured breakdown using clean markdown headings and bullet points separated by double newlines.\n"
                        "- Place each key role or relationship on its OWN distinct bullet point line:\n"
                        "  * **[Role / Attribute]:** [Entity or Description]\n"
                        "    > *Evidence:* \"[Direct quote excerpt]\" (Ch. X)\n"
                        "- NEVER place multiple bullet points on the same line or run them together."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        ans = completion.choices[0].message.content
        if ans and ans.strip():
            return ans.strip()
        return default_ans
    except Exception:
        return default_ans


def generate_grounded_collection_answer(collection_res: Dict[str, Any], question: str, chapter: int) -> str:
    """Synthesizes a fluent, grounded narrative answer for collection queries using the LLM when available."""
    default_ans = collection_res.get("answer", "")
    client, model = get_llm_client()
    if not client:
        return default_ans

    try:
        payload = {
            "question": question,
            "reader_current_chapter": chapter,
            "entities": collection_res.get("nodes", []),
            "investigators": collection_res.get("investigators", []),
            "relationships": collection_res.get("relationships", []),
            "evidence": collection_res.get("evidence", []),
        }

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are StoryGraph, a spoiler-safe mystery story assistant. "
                        "Answer the reader's question about story characters, members, or investigators up to their current chapter.\n\n"
                        "CRITICAL RULES:\n"
                        "1. Clearly distinguish each character's specific role (e.g. official police inspector vs consulting detective).\n"
                        "2. Explicitly cite the evidence excerpt supporting each person.\n"
                        "3. Do NOT reveal or invent any plot details beyond the reader's current chapter.\n"
                        "4. Keep the explanation direct, professional, and clear.\n\n"
                        "FORMATTING RULES:\n"
                        "- Begin with a direct summary of the individuals identified.\n"
                        "- Format each person on their OWN distinct bullet point line separated by blank lines:\n"
                        "  * **[Name]** ([Specific Role or Title]): [Brief description of their role]\n"
                        "    > *Evidence:* \"[Direct quote excerpt]\" (Ch. X)\n"
                        "- Never bunch multiple bullet points onto a single line."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        ans = completion.choices[0].message.content
        if ans and ans.strip():
            return ans.strip()
        return default_ans
    except Exception:
        return default_ans

