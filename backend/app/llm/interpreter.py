"""Question interpretation and spoiler-safe entity resolution."""
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.graph.explorer import get_visible_entities, resolve_entity


def _extract_entities_via_llm(question: str, chapter: int) -> Optional[Tuple[str, str]]:
    """Extracts entity mention strings from a natural language question using OpenAI tool calling."""
    if not OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract the two fictional entities (characters, events, locations, factions) "
                        "the reader is asking to connect or relate. "
                        "Call the select_entities tool with entity_a and entity_b. "
                        "Do not answer the question or make assumptions."
                    ),
                },
                {"role": "user", "content": f"Reader progress: Chapter {chapter}. Question: {question}"},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "select_entities",
                        "description": "Select the two named story entities to connect.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "entity_a": {"type": "string", "description": "First entity name or mention"},
                                "entity_b": {"type": "string", "description": "Second entity name or mention"},
                            },
                            "required": ["entity_a", "entity_b"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "select_entities"}},
            temperature=0.0,
        )
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            return None
        args = json.loads(tool_calls[0].function.arguments)
        return args.get("entity_a", "").strip(), args.get("entity_b", "").strip()
    except Exception:
        # LLM failure or network timeout: fall back gracefully to rule-based extractor
        return None


def _extract_entities_fallback(question: str, chapter: int) -> Optional[Tuple[str, str]]:
    """Deterministic fallback entity extraction matching visible entity names/aliases in question."""
    visible = get_visible_entities(chapter)
    # Collect candidate names sorted by descending length to match full names first
    candidates = []
    for item in visible:
        name = item["name"]
        if name:
            candidates.append(name)
        for alias in item.get("aliases", []):
            if alias:
                candidates.append(alias)

    candidates = sorted(list(set(candidates)), key=len, reverse=True)
    found_mentions: List[str] = []
    q_lower = question.lower()

    for cand in candidates:
        # Word boundary match
        pattern = r"\b" + re.escape(cand.lower()) + r"\b"
        if re.search(pattern, q_lower):
            # Check if this candidate is not just a substring of an already found mention
            if not any(cand.lower() in existing.lower() for existing in found_mentions):
                found_mentions.append(cand)
        if len(found_mentions) == 2:
            break

    if len(found_mentions) >= 2:
        return found_mentions[0], found_mentions[1]

    # Try heuristic pattern: "How is X connected to Y?", "relationship between X and Y"
    patterns = [
        r"(?:how (?:are|is)|connect(?:ion)? between)\s+([A-Za-z\s'\.]+?)\s+(?:and|to|with)\s+([A-Za-z\s'\.]+?)(?:\?|$|\.|\s+in\b)",
        r"(?:relationship between)\s+([A-Za-z\s'\.]+?)\s+(?:and|with)\s+([A-Za-z\s'\.]+?)(?:\?|$|\.)",
    ]
    for pat in patterns:
        m = re.search(pat, question, re.IGNORECASE)
        if m:
            ea = m.group(1).strip()
            eb = m.group(2).strip()
            # Clean common filler words
            ea = re.sub(r"^(the|dr\.|mr\.|mrs\.|ms\.)\s+", "", ea, flags=re.IGNORECASE)
            eb = re.sub(r"^(the|dr\.|mr\.|mrs\.|ms\.)\s+", "", eb, flags=re.IGNORECASE)
            return ea, eb

    return None


def interpret_question(question: str, chapter: int) -> Dict[str, Any]:
    """Interprets reader question, extracts entity pair, and validates against visible graph at chapter."""
    # 1. Extract entity mentions (LLM first if configured, then deterministic fallback)
    extracted = _extract_entities_via_llm(question, chapter)
    if not extracted or not extracted[0] or not extracted[1]:
        extracted = _extract_entities_fallback(question, chapter)

    if not extracted or not extracted[0] or not extracted[1]:
        return {
            "status": "clarification_needed",
            "answer": (
                f"I could not clearly identify two story entities to connect in your question for Chapter {chapter}. "
                "Please specify the names of two characters, events, locations, or factions."
            ),
            "entities": [],
            "resolved_entities": [],
        }

    mention_a, mention_b = extracted

    # 2. Resolve each mention against the visible graph
    found_a = resolve_entity(mention_a, chapter)
    found_b = resolve_entity(mention_b, chapter)

    # 3. Check for unresolved names (0 matches)
    unresolved = []
    if len(found_a) == 0:
        unresolved.append(mention_a)
    if len(found_b) == 0:
        unresolved.append(mention_b)

    if unresolved:
        unresolved_str = " and ".join(f"'{u}'" for u in unresolved)
        return {
            "status": "unresolved_entity",
            "answer": (
                f"I could not identify {unresolved_str} in the story revealed up to Chapter {chapter}. "
                "Please check the spelling or ask about entities revealed by this point in the narrative."
            ),
            "entities": {"entity_a": found_a, "entity_b": found_b},
            "resolved_entities": [],
        }

    # 4. Check for ambiguous names (> 1 match)
    ambiguous = []
    clarification_options = []
    if len(found_a) > 1:
        names = [item["name"] for item in found_a]
        ambiguous.append(f"'{mention_a}' (could refer to: {', '.join(names)})")
        clarification_options.extend(found_a)
    if len(found_b) > 1:
        names = [item["name"] for item in found_b]
        ambiguous.append(f"'{mention_b}' (could refer to: {', '.join(names)})")
        clarification_options.extend(found_b)

    if ambiguous:
        amb_str = "; ".join(ambiguous)
        return {
            "status": "clarification_needed",
            "answer": (
                f"Clarification needed: {amb_str}. "
                "Please clarify which specific entity you are asking about."
            ),
            "entities": {"entity_a": found_a, "entity_b": found_b},
            "resolved_entities": [],
            "ambiguous_options": clarification_options,
        }

    # 5. Exactly 1 match for each
    return {
        "status": "resolved",
        "resolved_entities": [found_a[0], found_b[0]],
        "entities": [found_a[0], found_b[0]],
    }
