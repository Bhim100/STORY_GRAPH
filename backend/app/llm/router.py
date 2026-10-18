"""Deterministic question router for StoryGraph narrative question answering.

Classifies incoming reader queries into 5 structured question types:
1. connection between two entities (connection)
2. profile of one entity (entity_profile)
3. collection/list query (collection_query)
4. event or evidence query (event_evidence)
5. culprit or "who did it?" query (culprit_query)
or unsupported/unrelated queries.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from app.config import ROOT_DIR
# Import from app.llm.interpreter so test mocks on interpreter functions are respected
from app.llm.interpreter import get_visible_entities, resolve_entity


class QuestionType:
    CONNECTION = "connection"
    ENTITY_PROFILE = "entity_profile"
    COLLECTION_QUERY = "collection_query"
    EVENT_EVIDENCE = "event_evidence"
    CULPRIT_QUERY = "culprit_query"
    UNSUPPORTED = "unsupported"


_DATASET_CACHE: Optional[Dict[str, Any]] = None


def _load_story_dataset() -> Dict[str, Any]:
    """Loads glass_orchard.json story dataset from disk for known entity metadata."""
    global _DATASET_CACHE
    if _DATASET_CACHE is not None:
        return _DATASET_CACHE

    json_path = ROOT_DIR / "data" / "stories" / "glass_orchard.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                _DATASET_CACHE = json.load(f)
                return _DATASET_CACHE
        except Exception:
            pass
    return {}


def get_all_story_entities() -> List[Dict[str, Any]]:
    """Returns all known story entities from the story dataset across all chapters."""
    dataset = _load_story_dataset()
    entities: List[Dict[str, Any]] = []

    for c in dataset.get("characters", []):
        entities.append({
            "id": c["id"],
            "name": c["name"],
            "aliases": c.get("aliases", []),
            "labels": ["Character"],
            "reveal_chapter": c.get("reveal_chapter", 1),
            "role": c.get("role", ""),
        })

    for loc in dataset.get("locations", []):
        entities.append({
            "id": loc["id"],
            "name": loc["name"],
            "aliases": [],
            "labels": ["Location"],
            "reveal_chapter": loc.get("reveal_chapter", 1),
        })

    for fac in dataset.get("factions", []):
        entities.append({
            "id": fac["id"],
            "name": fac["name"],
            "aliases": [],
            "labels": ["Faction"],
            "reveal_chapter": fac.get("reveal_chapter", 1),
        })

    for ev in dataset.get("events", []):
        entities.append({
            "id": ev["id"],
            "name": ev["title"],
            "aliases": [],
            "labels": ["Event"],
            "reveal_chapter": ev.get("reveal_chapter", 1),
        })

    return entities


def extract_entity_mentions(question: str, chapter: int) -> List[str]:
    """Deterministically extracts candidate entity name/alias mentions from the question."""
    visible = []
    try:
        visible = get_visible_entities(chapter)
    except Exception:
        pass

    all_entities = get_all_story_entities()

    # Collect all candidate strings (names and aliases)
    candidate_set: Set[str] = set()
    for item in visible + all_entities:
        name = item.get("name")
        if name and len(name.strip()) > 1:
            candidate_set.add(name.strip())
        for alias in item.get("aliases", []):
            if alias and len(alias.strip()) > 1:
                candidate_set.add(alias.strip())

    COMMON_ALIASES = [
        "The Greenhouse", "greenhouse", "the greenhouse",
        "Thorne Manor", "manor", "the manor",
        "The Harbor Inn", "harbor inn", "inn",
        "the death", "death", "Elias's death", "death of Elias",
        "harvest dinner", "the dinner", "dinner",
        "the quarrel", "quarrel", "the argument", "argument", "dispute",
        "the cider", "cider", "poisoned cider", "tampered cider",
        "the will", "will", "changed will", "will changed",
    ]
    candidate_set.update(COMMON_ALIASES)

    # Sort descending by length so full names match before parts ("Elias Thorne" before "Thorne")
    sorted_candidates = sorted(list(candidate_set), key=len, reverse=True)

    q_lower = question.lower()
    found_mentions: List[str] = []

    for cand in sorted_candidates:
        pattern = r"\b" + re.escape(cand.lower()) + r"\b"
        if re.search(pattern, q_lower):
            # Check if this candidate is not a substring of an already extracted mention
            if not any(cand.lower() in existing.lower() for existing in found_mentions):
                found_mentions.append(cand)

    # If entity candidates already matched, return them without noisy regex extraction
    if found_mentions:
        return found_mentions

    # Fallback heuristic regexes only when no candidates matched (e.g. unknown names)
    heuristic_patterns = [
        r"(?:how (?:are|is))\s+([A-Za-z\s'\.]+?)\s+(?:connected to|related to)\s+([A-Za-z\s'\.]+?)(?:\?|$|\.)",
        r"(?:how are|connect(?:ion)? between)\s+([A-Za-z\s'\.]+?)\s+and\s+([A-Za-z\s'\.]+?)(?:\?|$|\.|\s+in\b)",
        r"(?:relationship between)\s+([A-Za-z\s'\.]+?)\s+(?:and|with)\s+([A-Za-z\s'\.]+?)(?:\?|$|\.)",
        r"(?:tell\s+me\s+about|profile\s+of|describe|who\s+is|who\s+was|what\s+do\s+we\s+know\s+about)\s+([A-Za-z\s'\.]+?)(?:\?|$|\.)",
        r"(?:did)\s+([A-Za-z\s'\.]+?)\s+(?:kill|murder|poison)\s+([A-Za-z\s'\.]+?)(?:\?|$|\.)",
    ]

    COMMON_NON_ENTITY_WORDS = {
        "the story", "story", "each other", "anyone", "everyone",
        "culprit", "the culprit", "killer", "the killer", "murderer",
        "the murderer", "perpetrator", "the perpetrator", "poisoner",
        "the poisoner", "victim", "the victim", "suspect", "the suspect",
        "suspects", "characters", "people", "evidence", "events", "locations", "factions"
    }

    for pat in heuristic_patterns:
        m = re.search(pat, question, re.IGNORECASE)
        if m:
            for g in m.groups():
                cleaned = re.sub(r"^(?:the|dr\.|mr\.|mrs\.|ms\.)\s+", "", g.strip(), flags=re.IGNORECASE).strip()
                cleaned = cleaned.rstrip("?.,")
                if cleaned and len(cleaned) > 1 and not any(cleaned.lower() in ex.lower() for ex in found_mentions):
                    # Avoid common role words and stopwords
                    if cleaned.lower() not in COMMON_NON_ENTITY_WORDS:
                        found_mentions.append(cleaned)
            if found_mentions:
                break

    return found_mentions


# Classification pattern definitions
CULPRIT_PATTERNS = [
    r"\bwho\s+(?:is\s+the\s+)?(?:culprit|killer|murderer|perpetrator|poisoner)\b",
    r"\bwho\s+(?:killed|murdered|poisoned|attacked|slew|slayed)\b",
    r"\bwho\s+did\s+it\b",
    r"\bwhodunit\b",
    r"\bwho\s+(?:is\s+)?responsible\s+for\s+(?:the\s+)?(?:death|murder|killing|poisoning)\b",
    r"\bwho\s+committed\s+the\s+(?:murder|crime|poisoning)\b",
    r"\bdid\s+(.+?)\s+(?:kill|murder|poison)\b",
    r"\bis\s+(.+?)\s+the\s+(?:culprit|killer|murderer|perpetrator)\b",
]

COLLECTION_PATTERNS = [
    r"\blist\s+(?:all\s+)?(?:the\s+)?(?:characters|suspects|people|locations|factions|events|evidence|members)\b",
    r"\bwho\s+are\s+the\s+members\s+of\b",
    r"\bwho\s+(?:is|are)\s+(?:in|part\s+of|belonging\s+to|members?\s+of)\b",
    r"\bwho\s+belongs\s+to\b",
    r"\bwho\s+(?:is|lives|resides|works|stays)\s+(?:at|in)\b",
    r"\bmembers\s+of\b",
    r"\bshow\s+(?:all\s+)?(?:the\s+)?(?:characters|suspects|people|locations|factions|events|evidence)\b",
    r"\bwhat\s+(?:characters|entities|events|locations|factions)\s+(?:are|exist)\b",
    r"\bwhich\s+characters\s+(?:are|were)\b",
    r"\beveryone\s+who\b",
    r"\ball\s+(?:characters|suspects|factions|locations|events)\b",
    r"\ball\s+the\s+(?:characters|suspects|factions|locations|events)\b",
]

EVENT_EVIDENCE_PATTERNS = [
    r"\bwhat\s+happened\b",
    r"\bwhat\s+occurred\b",
    r"\bwhat\s+evidence\b",
    r"\bevidence\b",
    r"\bwhy\s+(?:was|is)\s+(.+?)\s+suspected\b",
    r"\bwhy\s+(?:did\s+anyone|do\s+we)\s+suspect\b",
    r"\bwhy\s+suspect\b",
    r"\bwhere\s+did\s+(.+?)\s+(?:happen|occur|take\s+place|die)\b",
    r"\bwhen\s+did\s+(.+?)\s+(?:happen|occur|take\s+place)\b",
    r"\bhow\s+did\s+(.+?)\s+die\b",
    r"\bdid\s+(.+?)\s+(?:happen|occur|take\s+place)\b",
    r"\bwhat\s+caused\s+(?:the\s+)?(?:death|murder|poisoning)\b",
    r"\bwhat\s+claims\b",
    r"\ballegations?\b",
]

CONNECTION_PATTERNS = [
    r"\bhow\s+(?:are|is)\s+(.+?)\s+(?:and|to|with)\s+(.+?)\s+(?:connected|related)\b",
    r"\bwhat\s+(?:is|are)\s+(?:the\s+)?(?:connection|relationship|link)\s+between\s+(.+?)\s+(?:and|with)\s+(.+?)\b",
    r"\blink\s+between\s+(.+?)\s+and\s+(.+?)\b",
    r"\bhow\s+do\s+(.+?)\s+and\s+(.+?)\s+know\s+each\s+other\b",
    r"\bconnect(?:ion)?\s+between\s+(.+?)\s+and\s+(.+?)\b",
    r"\bis\s+(.+?)\s+connected\s+to\s+(.+?)\b",
    r"\bexplain\s+the\s+link\s+between\s+(.+?)\s+and\s+(.+?)\b",
    r"\bexplain\s+how\s+(.+?)\s+(?:and|is\s+connected\s+to)\s+(.+?)\b",
]

PROFILE_PATTERNS = [
    r"^tell\s+me\s+about\s+(.+?)(?:\?|$|\.)",
    r"\bprofile\s+of\s+(.+?)(?:\?|$|\.)",
    r"\bwho\s+is\s+(?!the\s+(?:culprit|killer|murderer|perpetrator|poisoner))(.+?)(?:\?|$|\.)",
    r"\bwho\s+was\s+(?!the\s+(?:culprit|killer|murderer|perpetrator|poisoner))(.+?)(?:\?|$|\.)",
    r"\bdescribe\s+(?!the\s+evidence)(.+?)(?:\?|$|\.)",
    r"\bwhat\s+do\s+we\s+know\s+about\s+(.+?)(?:\?|$|\.)",
    r"\bwhat\s+is\s+(.+?)'s\s+(?:role|background|story)\b",
    r"\bdetails\s+(?:about|on)\s+(.+?)(?:\?|$|\.)",
    r"\bhow\s+is\s+(.+?)\s+connected\s+to\s+the\s+story\b",
]


def classify_question_type(question: str, extracted_mentions: List[str]) -> str:
    """Classifies question into one of the 5 question types or unsupported."""
    q_clean = question.strip()

    # 1. Culprit / Who did it queries take precedence
    for pat in CULPRIT_PATTERNS:
        if re.search(pat, q_clean, re.IGNORECASE):
            return QuestionType.CULPRIT_QUERY

    # 2. Collection / List queries
    for pat in COLLECTION_PATTERNS:
        if re.search(pat, q_clean, re.IGNORECASE):
            return QuestionType.COLLECTION_QUERY

    # 3. Event / Evidence queries
    for pat in EVENT_EVIDENCE_PATTERNS:
        if re.search(pat, q_clean, re.IGNORECASE):
            return QuestionType.EVENT_EVIDENCE

    # 4. Connection queries
    for pat in CONNECTION_PATTERNS:
        if re.search(pat, q_clean, re.IGNORECASE):
            return QuestionType.CONNECTION

    if len(extracted_mentions) >= 2:
        # Relational check
        if any(w in q_clean.lower() for w in ["connect", "relation", "link", "between", "know", "with", "and"]):
            return QuestionType.CONNECTION

    # 5. Entity profile queries
    for pat in PROFILE_PATTERNS:
        if re.search(pat, q_clean, re.IGNORECASE):
            return QuestionType.ENTITY_PROFILE

    if len(extracted_mentions) == 1:
        # Single entity query with descriptive or profile intent
        return QuestionType.ENTITY_PROFILE

    # 6. Fallback check: If no entities were extracted and no narrative mystery words match
    story_keywords = ["thorne", "voss", "halden", "reed", "quill", "calloway", "ames", "orchard", "greenhouse", "ledger", "cider", "murder", "poison", "will"]
    if not any(k in q_clean.lower() for k in story_keywords):
        return QuestionType.UNSUPPORTED

    return QuestionType.UNSUPPORTED


def route_question(question: str, chapter: int) -> Dict[str, Any]:
    """Routes reader question deterministically respecting chapter boundary visibility.

    Returns structured dict with:
    - question_type: QuestionType constant
    - status: 'ok', 'clarification_needed', 'unresolved_entity', or 'unsupported'
    - resolved_entities: list of resolved node dicts
    - ambiguous_options: list of candidate dicts when ambiguity occurs
    - unresolved_entities: list of entity mention strings that could not be resolved
    - answer: pre-formatted clarification or guidance string when needed
    """
    raw_mentions = extract_entity_mentions(question, chapter)
    q_type = classify_question_type(question, raw_mentions)

    if q_type == QuestionType.UNSUPPORTED:
        return {
            "question_type": QuestionType.UNSUPPORTED,
            "status": "unsupported",
            "resolved_entities": [],
            "ambiguous_options": [],
            "unresolved_entities": [],
            "answer": (
                "I cannot answer this question from the supported graph operations. "
                "Supported question types include connections between entities, entity profiles, "
                "collections/lists, events/evidence, and culprit queries regarding story elements "
                f"revealed up to Chapter {chapter}."
            ),
        }

    # Resolve each extracted mention against visible graph at chapter boundary
    resolved: List[Dict[str, Any]] = []
    ambiguous_mentions: List[str] = []
    ambiguous_options: List[Dict[str, Any]] = []
    unresolved: List[str] = []

    for mention in raw_mentions:
        matches = resolve_entity(mention, chapter)
        if len(matches) == 0:
            unresolved.append(mention)
        elif len(matches) > 1:
            names = [m["name"] for m in matches]
            ambiguous_mentions.append(f"'{mention}' (could refer to: {', '.join(names)})")
            ambiguous_options.extend(matches)
        else:
            resolved.append(matches[0])

    # Ambiguity check: prompt clarification
    if ambiguous_mentions:
        amb_str = "; ".join(ambiguous_mentions)
        return {
            "question_type": q_type,
            "status": "clarification_needed",
            "resolved_entities": resolved,
            "ambiguous_options": ambiguous_options,
            "unresolved_entities": unresolved,
            "answer": (
                f"Clarification needed: {amb_str}. "
                "Please clarify which specific entity you are asking about."
            ),
        }

    # Unresolved / hidden entity check (e.g., entity revealed in a future chapter)
    if unresolved:
        if q_type == QuestionType.CULPRIT_QUERY:
            return {
                "question_type": q_type,
                "status": "ok",
                "resolved_entities": resolved,
                "ambiguous_options": [],
                "unresolved_entities": unresolved,
                "answer": "",
            }
        unresolved_str = " and ".join(f"'{u}'" for u in unresolved)
        return {
            "question_type": q_type,
            "status": "unresolved_entity",
            "resolved_entities": resolved,
            "ambiguous_options": [],
            "unresolved_entities": unresolved,
            "answer": (
                f"I could not identify {unresolved_str} in the story revealed up to Chapter {chapter}. "
                "Please check the spelling or ask about entities revealed by this point in the narrative."
            ),
        }

    # If connection question, check that we have exactly or at least 2 distinct entities
    if q_type == QuestionType.CONNECTION:
        if len(resolved) < 2:
            return {
                "question_type": QuestionType.CONNECTION,
                "status": "clarification_needed",
                "resolved_entities": resolved,
                "ambiguous_options": [],
                "unresolved_entities": [],
                "answer": "Could not identify two distinct story entities to connect in this question.",
            }

    # If entity profile question, check that we have at least 1 entity
    if q_type == QuestionType.ENTITY_PROFILE:
        if len(resolved) == 0:
            return {
                "question_type": QuestionType.ENTITY_PROFILE,
                "status": "clarification_needed",
                "resolved_entities": [],
                "ambiguous_options": [],
                "unresolved_entities": [],
                "answer": "Please specify the name of the character, location, faction, or event you would like a profile for.",
            }

    return {
        "question_type": q_type,
        "status": "ok",
        "resolved_entities": resolved,
        "ambiguous_options": [],
        "unresolved_entities": [],
        "answer": "",
    }
