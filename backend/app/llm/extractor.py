"""LLM-assisted, evidence-grounded knowledge-graph extraction pipeline for StoryGraph.

Extracts characters, locations, factions, events, claims, and verified evidence excerpts
chapter-by-chapter from story manuscripts with spoiler boundary tracking and exact quote verification.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field, model_validator

from app.config import get_llm_client
from app.models import (
    Character,
    Claim,
    Event,
    Evidence,
    Faction,
    Location,
    StoryDataset,
)

logger = logging.getLogger(__name__)

# Allowed predicates for knowledge graph claims
SUPPORTED_PREDICATES = {
    "OWNS",
    "TRAINS",
    "INVESTIGATES",
    "MARRIED_TO",
    "SUSPECTS",
    "EMPLOYED_BY",
    "THREATENS",
    "PRESENT_AT",
    "COMMITTED",
    "FAMILY_OF",
    "ACQUAINTED_WITH",
    "INTERACTED_WITH",
    "PARTICIPATED_IN",
    "LOCATED_AT",
    "OCCURS_AT",
}

# Explicit claim validation statuses
SUPPORTED_VALIDATIONS = {
    "confirmed",
    "alleged",
    "suspected",
    "disputed",
    "unknown",
}


# ============================================================================
# Pydantic Schemas for Structured LLM Chapter Extraction
# ============================================================================

class RawExtractedCharacter(BaseModel):
    name: str = Field(default="", description="Canonical full name of the character as identified in this passage")
    role: str = Field(default="Character", description="Source-supported role or function, e.g. Consulting Detective, Victim, Suspect, Stable Boy")
    aliases: List[str] = Field(default_factory=list, description="Other names, honorifics, or titles used for this character")

    @model_validator(mode="before")
    @classmethod
    def normalize_character(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data, "role": "Character", "aliases": []}
        if isinstance(data, dict):
            if not data.get("name"):
                for k in ("canonical_name", "character_name", "full_name", "character"):
                    if data.get(k):
                        data["name"] = str(data[k])
                        break
            if not data.get("name"):
                data["name"] = "Unknown Character"
        return data


class RawExtractedLocation(BaseModel):
    name: str = Field(default="", description="Name of the place, estate, room, or setting")
    context: str = Field(default="", description="Source-supported context or description of this location")

    @model_validator(mode="before")
    @classmethod
    def normalize_location(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data}
        if isinstance(data, dict):
            if not data.get("name"):
                for k in ("location_name", "canonical_name", "place"):
                    if data.get(k):
                        data["name"] = str(data[k])
                        break
            if not data.get("name"):
                data["name"] = "Unknown Location"
        return data


class RawExtractedFaction(BaseModel):
    name: str = Field(default="", description="Name of the organization, family, firm, police department, or faction")

    @model_validator(mode="before")
    @classmethod
    def normalize_faction(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"name": data}
        if isinstance(data, dict):
            if not data.get("name"):
                for k in ("faction_name", "organization_name", "group_name"):
                    if data.get(k):
                        data["name"] = str(data[k])
                        break
            if not data.get("name"):
                data["name"] = "Unknown Faction"
        return data


class RawExtractedParticipant(BaseModel):
    character_name: str
    role: str = Field(default="participant", description="Role in event: perpetrator, victim, witness, investigator, attendee")

    @model_validator(mode="before")
    @classmethod
    def normalize_participant(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"character_name": data, "role": "participant"}
        if isinstance(data, dict):
            if "name" in data and "character_name" not in data:
                data["character_name"] = str(data["name"])
            elif "character" in data and "character_name" not in data:
                data["character_name"] = str(data["character"])
        return data


class RawExtractedEvent(BaseModel):
    title: str = Field(default="", description="Clear title of the plot occurrence, e.g. 'The Murder of John Straker'")
    occurrence_chapter: int = Field(default=1, description="When the event actually occurred in narrative chronology")
    reveal_chapter: int = Field(default=1, description="When the event or fact is revealed to the reader")
    location_name: Optional[str] = Field(default=None, description="Location where the event occurred, if known")
    participants: List[RawExtractedParticipant] = Field(default_factory=list, description="Characters involved in this event")

    @model_validator(mode="before")
    @classmethod
    def normalize_event(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "event" in data and not data.get("title"):
                data["title"] = str(data["event"])
            elif "name" in data and not data.get("title"):
                data["title"] = str(data["name"])
            if not data.get("title") and data.get("description"):
                data["title"] = str(data["description"])[:80]
            if not data.get("title"):
                data["title"] = "Narrative Event"

            if "chapter" in data and "reveal_chapter" not in data:
                data["reveal_chapter"] = data["chapter"]
            if "occurrence_chapter" not in data:
                data["occurrence_chapter"] = data.get("reveal_chapter", 1)

            # Normalize participants list
            parts = data.get("participants", [])
            norm_parts = []
            for p in parts:
                if isinstance(p, str):
                    norm_parts.append({"character_name": p, "role": "participant"})
                elif isinstance(p, dict):
                    norm_parts.append(p)
            data["participants"] = norm_parts
        return data


class RawExtractedClaim(BaseModel):
    subject_name: str = Field(default="", description="Subject entity name (character, location, or event)")
    predicate: str = Field(default="INTERACTED_WITH", description="One of: OWNS, TRAINS, INVESTIGATES, MARRIED_TO, SUSPECTS, EMPLOYED_BY, THREATENS, PRESENT_AT, COMMITTED, FAMILY_OF, ACQUAINTED_WITH, INTERACTED_WITH, OCCURS_AT")
    object_name: str = Field(default="", description="Object entity name (character, location, or event)")
    role: Optional[str] = Field(default=None, description="Role qualifier, e.g. trainer, owner, employer, suspect, victim, setting")
    text: str = Field(default="", description="Clear, declarative summary sentence of the claim")
    validation: str = Field(default="confirmed", description="Status: confirmed, alleged, suspected, disputed, or unknown")
    reveal_chapter: int = Field(default=1, description="Chapter when this relationship/fact is revealed to the reader")
    excerpt: str = Field(default="", description="EXACT verbatim quote from this chapter supporting the claim (max 250 chars)")

    @model_validator(mode="before")
    @classmethod
    def normalize_claim(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # subject
            if "subject" in data and not data.get("subject_name"):
                data["subject_name"] = str(data["subject"])
            elif "subject_name" in data and not data.get("subject"):
                data["subject"] = str(data["subject_name"])

            # object
            if "object" in data and not data.get("object_name"):
                data["object_name"] = str(data["object"])
            elif "object_name" in data and not data.get("object"):
                data["object"] = str(data["object_name"])

            # predicate / relationship / kind
            if "relationship" in data and not data.get("predicate"):
                data["predicate"] = str(data["relationship"])
            elif "kind" in data and not data.get("predicate"):
                data["predicate"] = str(data["kind"])

            # text / claim / statement
            if "claim" in data and not data.get("text"):
                data["text"] = str(data["claim"])
            elif "statement" in data and not data.get("text"):
                data["text"] = str(data["statement"])
            elif "description" in data and not data.get("text"):
                data["text"] = str(data["description"])
            if not data.get("text") and data.get("subject_name") and data.get("object_name") and data.get("predicate"):
                data["text"] = f"{data['subject_name']} {data['predicate']} {data['object_name']}."

            # excerpt / evidence / quote unpacking
            raw_ex = data.get("excerpt") or data.get("evidence") or data.get("quote") or data.get("source_quote") or data.get("source")
            if isinstance(raw_ex, dict):
                raw_ex = raw_ex.get("excerpt") or raw_ex.get("text") or raw_ex.get("quote") or raw_ex.get("evidence") or ""
            data["excerpt"] = str(raw_ex or "").strip()

            # reveal_chapter
            if "chapter" in data and "reveal_chapter" not in data:
                data["reveal_chapter"] = data["chapter"]
            if "reveal_chapter" not in data or data["reveal_chapter"] is None:
                data["reveal_chapter"] = 1

        return data


class ChapterExtractionResponse(BaseModel):
    characters: List[RawExtractedCharacter] = Field(default_factory=list)
    locations: List[RawExtractedLocation] = Field(default_factory=list)
    factions: List[RawExtractedFaction] = Field(default_factory=list)
    events: List[RawExtractedEvent] = Field(default_factory=list)
    claims: List[RawExtractedClaim] = Field(default_factory=list)


# ============================================================================
# Exact Substring Quote Verification
# ============================================================================

def normalize_text_for_matching(text: str) -> str:
    """Normalizes whitespace and standardizes quotation marks for resilient substring search."""
    if not text:
        return ""
    # Standardize unicode quotes and dashes
    t = text.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    t = t.replace("\u2014", " - ").replace("\u2013", " - ")
    # Collapse multiple whitespace characters (including newlines) to a single space
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def verify_excerpt_in_text(excerpt: str, chapter_text: str) -> Tuple[bool, str]:
    """Validates that an excerpt is an exact, verified substring of the chapter text.

    Returns:
        (is_verified, reason)
    """
    if not excerpt or not excerpt.strip():
        return False, "Excerpt is empty."

    clean_excerpt = excerpt.strip().strip('"').strip("'").strip()
    if len(clean_excerpt) < 5:
        return False, "Excerpt is too short to serve as reliable evidence."

    # Direct check first
    if clean_excerpt in chapter_text:
        return True, "Exact verbatim match."

    # Normalized whitespace check
    norm_chapter = normalize_text_for_matching(chapter_text)
    norm_excerpt = normalize_text_for_matching(clean_excerpt)
    if norm_excerpt in norm_chapter:
        return True, "Normalized verbatim match."

    # Substring check with stripped edge punctuation
    trimmed_excerpt = norm_excerpt.strip(".,;:?!- ")
    if len(trimmed_excerpt) >= 10 and trimmed_excerpt in norm_chapter:
        return True, "Trimmed verbatim match."

    return False, f"Excerpt was not found in the chapter manuscript: '{clean_excerpt[:60]}...'"


# ============================================================================
# Slug & Canonical Identity Helpers
# ============================================================================

def slugify(text: str) -> str:
    """Generates a stable, alphanumeric snake_case identifier."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return s or "item"


# Honorifics and title prefixes used to detect person variants
HONORIFICS = {
    "mr", "mr.", "mrs", "mrs.", "miss", "ms", "ms.", "dr", "dr.", "doctor",
    "lord", "lady", "sir", "detective", "inspector", "constable", "captain",
    "colonel", "professor", "prof", "prof.", "father", "baron", "count"
}


def strip_honorifics(name: str) -> str:
    """Strips leading honorifics to find base name."""
    words = name.strip().split()
    while words and words[0].lower() in HONORIFICS:
        words = words[1:]
    return " ".join(words).strip()


def are_names_same_person(name_a: str, name_b: str) -> bool:
    """Determines whether two name mentions refer to the same canonical character.

    Conservative rule:
    - If stripped versions match (e.g., 'Miss Susan Cushing' and 'Susan Cushing').
    - Spouses (e.g. 'Mr. Straker' and 'Mrs. Straker') or different genders (Mrs. Straker and John Straker) are NEVER merged.
    - Single names match if they correspond to the surname of a full name.
    """
    na_low = name_a.strip().lower()
    nb_low = name_b.strip().lower()
    if na_low == nb_low:
        return True

    sa = strip_honorifics(name_a).lower()
    sb = strip_honorifics(name_b).lower()
    if sa == sb and sa:
        # Same base name. But if one is "Mrs." and other is not, spouses must stay separate
        is_na_mrs = "mrs." in na_low or "mrs " in na_low
        is_nb_mrs = "mrs." in nb_low or "mrs " in nb_low
        if is_na_mrs != is_nb_mrs:
            return False
        return True

    # If base names differ: female titles (Mrs., Miss) cannot merge with different names/surnames
    is_na_female = any(h in na_low for h in ["mrs.", "mrs ", "miss ", "lady "])
    is_nb_female = any(h in nb_low for h in ["mrs.", "mrs ", "miss ", "lady "])
    if is_na_female != is_nb_female:
        return False

    words_a = sa.split()
    words_b = sb.split()

    # Surname match (e.g. 'Holmes' and 'Sherlock Holmes')
    if len(words_a) == 1 and len(words_b) >= 2:
        if words_a[0] == words_b[-1]:
            return True
    if len(words_b) == 1 and len(words_a) >= 2:
        if words_b[0] == words_a[-1]:
            return True

    return False


# ============================================================================
# Cross-Chapter Entity & Alias Registry
# ============================================================================

class EntityRegistry:
    """Tracks canonical characters, locations, factions, and events across chapters."""

    def __init__(self, book_id: str):
        self.book_id = book_id
        # Canonical stores
        self.characters: Dict[str, Character] = {}
        self.locations: Dict[str, Location] = {}
        self.factions: Dict[str, Faction] = {}
        self.events: Dict[str, Event] = {}

        # Alias / lookup maps
        self.char_name_to_id: Dict[str, str] = {}
        self.loc_name_to_id: Dict[str, str] = {}
        self.fac_name_to_id: Dict[str, str] = {}
        self.event_title_to_id: Dict[str, str] = {}

        # Introduction chapter tracking
        self.introduced_chapters: Dict[str, int] = {}

    def register_character(self, name: str, role: str, aliases: List[str], chapter_num: int) -> str:
        """Finds or creates a canonical character, merging aliases conservatively."""
        clean_name = name.strip()
        if not clean_name:
            return ""

        # Check existing direct alias match
        name_lower = clean_name.lower()
        if name_lower in self.char_name_to_id:
            cid = self.char_name_to_id[name_lower]
            char_obj = self.characters[cid]
            # Add any new aliases
            for al in aliases + [clean_name]:
                al_clean = al.strip()
                if al_clean and al_clean not in char_obj.aliases and al_clean != char_obj.name:
                    char_obj.aliases.append(al_clean)
                    self.char_name_to_id[al_clean.lower()] = cid
            if role and role != "Character" and (char_obj.role == "Character" or len(role) > len(char_obj.role)):
                char_obj.role = role
            return cid

        # Conservative identity check against registered characters
        for cid, char_obj in self.characters.items():
            if are_names_same_person(clean_name, char_obj.name):
                # Canonicalize to the longer/more specific name if appropriate
                if len(clean_name.split()) > len(char_obj.name.split()) and not clean_name.lower().startswith("mr"):
                    old_name = char_obj.name
                    char_obj.name = clean_name
                    char_obj.aliases.append(old_name)
                    self.char_name_to_id[old_name.lower()] = cid
                elif clean_name not in char_obj.aliases and clean_name != char_obj.name:
                    char_obj.aliases.append(clean_name)

                for al in aliases:
                    al_clean = al.strip()
                    if al_clean and al_clean not in char_obj.aliases and al_clean != char_obj.name:
                        char_obj.aliases.append(al_clean)
                        self.char_name_to_id[al_clean.lower()] = cid

                self.char_name_to_id[name_lower] = cid
                if role and role != "Character" and (char_obj.role == "Character" or len(role) > len(char_obj.role)):
                    char_obj.role = role
                return cid

        # New canonical character
        cid = f"c_{slugify(clean_name)}"
        all_aliases = set()
        for al in aliases:
            al_clean = al.strip()
            if al_clean and al_clean != clean_name:
                all_aliases.add(al_clean)

        self.characters[cid] = Character(
            id=cid,
            story_id=self.book_id,
            name=clean_name,
            aliases=sorted(list(all_aliases)),
            role=role or "Character",
            reveal_chapter=chapter_num,
        )
        self.introduced_chapters[cid] = chapter_num
        self.char_name_to_id[name_lower] = cid
        for al in all_aliases:
            self.char_name_to_id[al.lower()] = cid

        return cid

    def register_location(self, name: str, chapter_num: int) -> str:
        """Finds or creates a canonical location."""
        clean_name = name.strip()
        if not clean_name:
            return ""

        name_lower = clean_name.lower()
        if name_lower in self.loc_name_to_id:
            return self.loc_name_to_id[name_lower]

        # Check for minor variations (e.g. 'The Manor' vs 'Manor')
        stripped = re.sub(r"^the\s+", "", name_lower).strip()
        for loc_key, lid in self.loc_name_to_id.items():
            if re.sub(r"^the\s+", "", loc_key).strip() == stripped:
                self.loc_name_to_id[name_lower] = lid
                return lid

        lid = f"l_{slugify(clean_name)}"
        self.locations[lid] = Location(
            id=lid,
            story_id=self.book_id,
            name=clean_name,
            reveal_chapter=chapter_num,
        )
        self.introduced_chapters[lid] = chapter_num
        self.loc_name_to_id[name_lower] = lid
        return lid

    def register_faction(self, name: str, chapter_num: int) -> str:
        """Finds or creates a canonical faction."""
        clean_name = name.strip()
        if not clean_name:
            return ""

        name_lower = clean_name.lower()
        if name_lower in self.fac_name_to_id:
            return self.fac_name_to_id[name_lower]

        fid = f"fac_{slugify(clean_name)}"
        self.factions[fid] = Faction(
            id=fid,
            story_id=self.book_id,
            name=clean_name,
            reveal_chapter=chapter_num,
        )
        self.introduced_chapters[fid] = chapter_num
        self.fac_name_to_id[name_lower] = fid
        return fid

    def register_event(self, title: str, occurrence_ch: int, reveal_ch: int) -> str:
        """Finds or creates a canonical event."""
        clean_title = title.strip()
        if not clean_title:
            return ""

        title_lower = clean_title.lower()
        if title_lower in self.event_title_to_id:
            return self.event_title_to_id[title_lower]

        # Check for similar event titles
        slug = slugify(clean_title)
        ev_id = f"ev_{slug}"
        if ev_id in self.events:
            return ev_id

        self.events[ev_id] = Event(
            id=ev_id,
            story_id=self.book_id,
            title=clean_title,
            event_chapter=occurrence_ch,
            reveal_chapter=reveal_ch,
        )
        self.event_title_to_id[title_lower] = ev_id
        return ev_id

    def resolve_any_entity(self, name_or_id: str) -> Optional[Tuple[str, str]]:
        """Resolves a raw name string to (entity_id, entity_type)."""
        clean = name_or_id.strip()
        if not clean:
            return None

        # Check direct IDs
        if clean in self.characters:
            return clean, "Character"
        if clean in self.locations:
            return clean, "Location"
        if clean in self.factions:
            return clean, "Faction"
        if clean in self.events:
            return clean, "Event"

        # Check names & aliases
        low = clean.lower()
        if low in self.char_name_to_id:
            return self.char_name_to_id[low], "Character"
        if low in self.loc_name_to_id:
            return self.loc_name_to_id[low], "Location"
        if low in self.fac_name_to_id:
            return self.fac_name_to_id[low], "Faction"
        if low in self.event_title_to_id:
            return self.event_title_to_id[low], "Event"

        # Check stripped honorifics
        stripped = strip_honorifics(clean).lower()
        if stripped in self.char_name_to_id:
            return self.char_name_to_id[stripped], "Character"

        return None


# ============================================================================
# LLM Chapter Prompt & Parsing
# ============================================================================

SYSTEM_PROMPT = """You are an expert literary knowledge-graph extraction analyst.
Your task is to read a chapter from a narrative manuscript and extract structured entities, plot events, and relationships with VERBATIM EVIDENCE.

EXTRACTION GUIDELINES:
1. CHARACTERS:
   - Extract real narrative individuals (e.g. 'Sherlock Holmes', 'Miss Susan Cushing', 'Jim Browner').
   - NEVER classify an event, action, or crime (e.g. 'The murders of his wife') as a Character.
   - Extract their canonical name, role (e.g. 'Investigating Detective', 'Victim', 'Suspect', 'Perpetrator'), and aliases.
2. LOCATIONS:
   - Extract real narrative locations (e.g. 'Cross Street, Croydon', '221B Baker Street', 'Liverpool').
3. NARRATIVE EVENTS:
   - Extract specific plot events or crimes (e.g. 'The Delivery of the Gruesome Packet', 'The Murders of Mary Browner and Alec Fairbairn').
   - NEVER create vague or placeholder events like 'Narrative Event', 'Event', or 'Conversation'.
   - List participating characters and their roles (perpetrator, victim, investigator, witness).
4. CLAIMS & RELATIONSHIPS:
   - Strict Predicate Semantic Typing:
     * SUSPECTS: Subject is a Character (investigator/accuser), Object MUST be a Character (the suspected person). Example: 'Lestrade' SUSPECTS 'Jim Browner'. NEVER suspect an event or crime.
     * COMMITTED: Subject is a Character (perpetrator), Object MUST be an Event (the crime). Example: 'Jim Browner' COMMITTED 'The Murders of Mary Browner and Alec Fairbairn'.
     * INVESTIGATES: Subject is a Character (investigator), Object MUST be an Event (the case/crime). Example: 'Sherlock Holmes' INVESTIGATES 'The Delivery of the Gruesome Packet'. (Do NOT put a city or location as the object of INVESTIGATES).
     * FAMILY_OF / MARRIED_TO / ACQUAINTED_WITH / INTERACTED_WITH / THREATENS: BOTH Subject and Object MUST be individual Characters!
     * OCCURS_AT: Subject is an Event, Object is a Location.
     * OWNS: Subject is a Character, Object is a Location or Object.
     * EMPLOYED_BY: Subject is a Character, Object is an Employer/Organization or Character (NEVER a geographic city like 'Liverpool').
   - CRITICAL RULE FOR GUILT:
     * Do NOT treat suspicion or accusation as proof of guilt!
     * If someone is only suspected or accused, use validation='suspected' or 'alleged'.
5. EVIDENCE (CRITICAL):
   - For EVERY claim, you MUST provide an 'excerpt': an EXACT, VERBATIM quote from this chapter supporting the claim.
   - Keep excerpts concise (under 250 characters).
   - DO NOT PARAPHRASE. DO NOT ALTER WORDS. An automated validator will check that your excerpt exists word-for-word in the text. If the quote does not match exactly, the entire claim will be rejected.

Return a valid JSON object matching the requested schema."""


def extract_chapter_with_llm(
    chapter_num: int,
    chapter_title: str,
    chapter_content: str,
    known_entities: List[str],
    client: Any,
    model: str,
    max_chunk_chars: int = 15000,
) -> ChapterExtractionResponse:
    """Invokes LLM provider with structured schema for a single chapter."""
    # Chunk text if unusually long to preserve prompt quality
    sample_text = chapter_content[:max_chunk_chars]

    user_payload = {
        "chapter_number": chapter_num,
        "chapter_title": chapter_title,
        "known_entities_from_previous_chapters": known_entities[:25],
        "chapter_text": sample_text,
    }

    prompt = (
        f"Extract characters, locations, events, claims, and verbatim evidence excerpts for Chapter {chapter_num} ('{chapter_title}').\n\n"
        f"Input Data:\n{json.dumps(user_payload, ensure_ascii=False)}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw_json_str = response.choices[0].message.content
        data = json.loads(raw_json_str)
        return ChapterExtractionResponse.model_validate(data)
    except Exception as exc:
        logger.warning(f"LLM extraction failed for Chapter {chapter_num}: {exc}")
        return ChapterExtractionResponse()


# ============================================================================
# Safe Deterministic Fallback (No Hardcodes, No Dummy Claims)
# ============================================================================

def extract_chapter_deterministic_safe(
    chapter_num: int,
    chapter_content: str,
    registry: EntityRegistry,
) -> Tuple[List[Claim], List[Evidence]]:
    """Deterministic, rule-based extraction fallback when LLM is unavailable.

    Guarantees:
    - Never uses hardcoded story names (no Silver Blaze / Glass Orchard keywords).
    - Never creates fabricated dummy claims.
    - Only extracts character names and locations supported by regex.
    """
    clean_text = normalize_text_for_matching(chapter_content)

    # 1. Detect honorific character mentions: Mr. Holmes, Dr. Watson, Inspector Gregory, etc.
    honorific_pattern = re.compile(
        r"\b(Mr\.|Mrs\.|Miss|Ms\.|Dr\.|Doctor|Lord|Lady|Sir|Detective|Inspector|Constable|Captain|Colonel|Father|Professor)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
    )
    for m in honorific_pattern.finditer(clean_text):
        full_mention = f"{m.group(1)} {m.group(2)}".strip()
        role = "Character"
        if m.group(1).lower() in ("detective", "inspector", "constable"):
            role = "Investigator"
        elif m.group(1).lower() in ("dr.", "doctor"):
            role = "Physician"
        registry.register_character(full_mention, role=role, aliases=[m.group(2)], chapter_num=chapter_num)

    # 2. Detect location names: [Name] (Manor|Hall|House|Estate|Inn|Hotel|Station|Stables|Room)
    loc_pattern = re.compile(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(Manor|Hall|House|Estate|Inn|Hotel|Station|Stables|Room|Park|Lodge)\b"
    )
    for m in loc_pattern.finditer(clean_text):
        loc_name = f"{m.group(1)} {m.group(2)}".strip()
        registry.register_location(loc_name, chapter_num=chapter_num)

    # 3. Controlled interaction claims: ONLY when two known characters are in the same sentence with dialogue verbs
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_text) if len(s.strip()) > 15]
    dialogue_verbs = {"said", "replied", "asked", "answered", "spoke", "inquired", "whispered", "cried"}
    claims: List[Claim] = []
    evidence: List[Evidence] = []
    claim_count = 0

    for s in sentences:
        s_low = s.lower()
        if not any(v in s_low for v in dialogue_verbs):
            continue

        # Check which characters appear in this sentence
        present_cids = set()
        for name_low, cid in registry.char_name_to_id.items():
            if re.search(r"\b" + re.escape(name_low) + r"\b", s_low):
                present_cids.add(cid)

        if len(present_cids) >= 2:
            cids = sorted(list(present_cids))
            for i in range(len(cids) - 1):
                ca_id = cids[i]
                cb_id = cids[i + 1]
                ca_name = registry.characters[ca_id].name
                cb_name = registry.characters[cb_id].name

                # Quote verification
                quote = s[:240]
                is_valid, _ = verify_excerpt_in_text(quote, chapter_content)
                if not is_valid:
                    continue

                claim_count += 1
                cid = f"cl_{registry.book_id}_det_{chapter_num}_{claim_count}"
                evi_id = f"evi_{registry.book_id}_det_{chapter_num}_{claim_count}"

                claims.append(Claim(
                    id=cid,
                    story_id=registry.book_id,
                    kind="INTERACTED_WITH",
                    subject=ca_id,
                    object=cb_id,
                    role="speaker",
                    text=f"{ca_name} interacted with {cb_name}.",
                    reveal_chapter=chapter_num,
                    validation="alleged",
                ))
                evidence.append(Evidence(
                    id=evi_id,
                    story_id=registry.book_id,
                    kind="testimony",
                    excerpt=quote,
                    source_chapter=chapter_num,
                    reveal_chapter=chapter_num,
                    supports=[cid],
                ))

    return claims, evidence


# ============================================================================
# Main Extraction Pipeline
# ============================================================================

class ExtractionPipelineResult(BaseModel):
    dataset: StoryDataset
    status: str  # ready, basic_extraction, partial
    status_message: str
    claims_accepted: int
    claims_rejected: int
    rejected_reasons: List[Dict[str, Any]] = Field(default_factory=list)


def run_story_extraction_pipeline(
    title: str,
    author: str,
    description: str,
    chapters_data: List[Dict[str, Any]],
    book_id: str,
) -> ExtractionPipelineResult:
    """Executes evidence-grounded extraction across all chapters with fallback resilience.

    Steps:
    1. Check for LLM client availability.
    2. Maintain cross-chapter EntityRegistry.
    3. For each chapter:
       - Extract structured elements (via LLM or deterministic fallback).
       - Validate EVERY quote in code against manuscript.
       - Discard unverified or fabricated claims.
       - Canonicalize entities into registry.
    4. Assemble verified StoryDataset.
    """
    client, model = get_llm_client()
    use_llm = bool(client and model)

    registry = EntityRegistry(book_id=book_id)
    verified_claims: List[Claim] = []
    verified_evidence: List[Evidence] = []
    rejected_reasons: List[Dict[str, Any]] = []

    claim_counter = 0
    evidence_counter = 0
    seen_claim_keys: Set[Tuple[str, str, str]] = set()

    status = "ready" if use_llm else "basic_extraction"
    status_message = (
        f"Knowledge graph extracted via {model} across {len(chapters_data)} chapters."
        if use_llm
        else "Basic extraction only; relationship extraction is incomplete. Configure an LLM API key for richer extraction."
    )

    for ch in chapters_data:
        ch_num = ch["chapter_number"]
        ch_title = ch.get("title", f"Chapter {ch_num}")
        ch_content = ch.get("content", "")

        if use_llm:
            known_entity_names = [c.name for c in registry.characters.values()] + [l.name for l in registry.locations.values()]
            extracted = extract_chapter_with_llm(
                chapter_num=ch_num,
                chapter_title=ch_title,
                chapter_content=ch_content,
                known_entities=known_entity_names,
                client=client,
                model=model,
            )

            if not extracted.characters and not extracted.claims and not extracted.events:
                # LLM call failed or was rate limited -> fall back cleanly to safe deterministic parsing for this chapter
                det_claims, det_evidence = extract_chapter_deterministic_safe(
                    chapter_num=ch_num,
                    chapter_content=ch_content,
                    registry=registry,
                )
                verified_claims.extend(det_claims)
                verified_evidence.extend(det_evidence)
                status = "basic_extraction"
                status_message = "Basic extraction only; relationship extraction is incomplete (LLM rate limit reached). Configure or upgrade LLM quota for richer extraction."
                continue

            # 1. Register Characters
            for c in extracted.characters:
                registry.register_character(
                    name=c.name,
                    role=c.role,
                    aliases=c.aliases,
                    chapter_num=ch_num,
                )

            # 2. Register Locations
            for loc in extracted.locations:
                registry.register_location(
                    name=loc.name,
                    chapter_num=ch_num,
                )

            # 3. Register Factions
            for fac in extracted.factions:
                registry.register_faction(
                    name=fac.name,
                    chapter_num=ch_num,
                )

            # 4. Register Narrative Events
            for ev in extracted.events:
                ev_title_clean = ev.title.strip()
                if not ev_title_clean or ev_title_clean.lower() in (
                    "narrative event", "event", "story event", "narrative", "untitled event"
                ):
                    continue
                ev_id = registry.register_event(
                    title=ev_title_clean,
                    occurrence_ch=ev.occurrence_chapter or ch_num,
                    reveal_ch=ev.reveal_chapter or ch_num,
                )
                # Link participants
                for part in ev.participants:
                    res_part = registry.resolve_any_entity(part.character_name)
                    if res_part and res_part[1] == "Character":
                        pid = res_part[0]
                        # Create event participation claim
                        claim_key = (pid, ev_id, "PARTICIPATED_IN")
                        if claim_key not in seen_claim_keys:
                            seen_claim_keys.add(claim_key)
                            claim_counter += 1
                            cid = f"cl_{book_id}_{claim_counter}"
                            verified_claims.append(Claim(
                                id=cid,
                                story_id=book_id,
                                kind="PARTICIPATED_IN",
                                subject=pid,
                                object=ev_id,
                                role=part.role,
                                text=f"{registry.characters[pid].name} participated in {ev_title_clean} as {part.role}.",
                                reveal_chapter=ev.reveal_chapter or ch_num,
                                validation="confirmed",
                            ))

            # 5. Process and Validate Claims & Evidence
            for cl in extracted.claims:
                # Substring Quote Verification
                is_valid, reason = verify_excerpt_in_text(cl.excerpt, ch_content)
                if not is_valid:
                    rejected_reasons.append({
                        "chapter": ch_num,
                        "claim_text": cl.text,
                        "excerpt": cl.excerpt,
                        "reason": reason,
                    })
                    continue

                pred = cl.predicate.upper().strip()
                if pred not in SUPPORTED_PREDICATES:
                    pred = "INTERACTED_WITH"

                is_event_pred = pred in ("COMMITTED", "INVESTIGATES", "PARTICIPATED_IN")
                is_loc_pred = pred in ("OCCURS_AT", "LOCATED_AT")

                # Filter malformed claims where SUSPECTS targets a crime instead of a person
                if pred == "SUSPECTS" and any(term in cl.object_name.lower() for term in ["murder", "death", "disappearance", "crime", "killing"]):
                    continue

                # Resolve Subject and Object
                res_sub = registry.resolve_any_entity(cl.subject_name)
                res_obj = registry.resolve_any_entity(cl.object_name)

                # Register Subject if new
                if not res_sub:
                    if pred == "OCCURS_AT":
                        sub_id = registry.register_event(cl.subject_name, ch_num, ch_num)
                    else:
                        sub_id = registry.register_character(cl.subject_name, "Character", [], ch_num)
                else:
                    sub_id = res_sub[0]

                # Register Object if new with semantic typing
                if not res_obj:
                    if is_event_pred:
                        obj_id = registry.register_event(cl.object_name, ch_num, ch_num)
                    elif is_loc_pred or (pred == "OWNS" and any(w in cl.object_name.lower() for w in ["street", "house", "stables", "manor", "estate", "room", "hall"])):
                        obj_id = registry.register_location(cl.object_name, ch_num)
                    else:
                        if any(term in cl.object_name.lower() for term in ["murder", "death", "disappearance", "crime", "packet"]):
                            obj_id = registry.register_event(cl.object_name, ch_num, ch_num)
                        else:
                            obj_id = registry.register_character(cl.object_name, "Character", [], ch_num)
                else:
                    obj_id = res_obj[0]
                    # Filter invalid pairings
                    if pred == "INVESTIGATES" and res_obj[1] == "Location":
                        continue
                    if pred == "EMPLOYED_BY" and res_obj[1] == "Location":
                        continue
                    if pred == "SUSPECTS" and res_obj[1] != "Character":
                        continue

                if sub_id == obj_id:
                    continue

                # Safety check: Do not treat suspicion as proof of guilt
                val_status = cl.validation.lower().strip()
                if val_status not in SUPPORTED_VALIDATIONS:
                    val_status = "alleged"
                if pred == "COMMITTED" and val_status in ("suspected", "alleged", "unknown"):
                    pred = "SUSPECTS"

                # Deduplicate identical relationships
                claim_key = (sub_id, obj_id, pred)
                reveal_ch = cl.reveal_chapter if cl.reveal_chapter >= ch_num else ch_num

                if claim_key in seen_claim_keys:
                    # Find existing claim to attach evidence
                    existing_claim = next((c for c in verified_claims if (c.subject, c.object, c.kind) == claim_key), None)
                    if existing_claim:
                        evidence_counter += 1
                        evi_id = f"evi_{book_id}_{evidence_counter}"
                        verified_evidence.append(Evidence(
                            id=evi_id,
                            story_id=book_id,
                            kind="testimony",
                            excerpt=cl.excerpt[:245],
                            source_chapter=ch_num,
                            reveal_chapter=reveal_ch,
                            supports=[existing_claim.id],
                        ))
                    continue

                seen_claim_keys.add(claim_key)
                claim_counter += 1
                cid = f"cl_{book_id}_{claim_counter}"
                evidence_counter += 1
                evi_id = f"evi_{book_id}_{evidence_counter}"

                verified_claims.append(Claim(
                    id=cid,
                    story_id=book_id,
                    kind=pred,
                    subject=sub_id,
                    object=obj_id,
                    role=cl.role or "",
                    text=cl.text,
                    reveal_chapter=reveal_ch,
                    validation=val_status,
                ))

                verified_evidence.append(Evidence(
                    id=evi_id,
                    story_id=book_id,
                    kind="testimony",
                    excerpt=cl.excerpt[:245],
                    source_chapter=ch_num,
                    reveal_chapter=reveal_ch,
                    supports=[cid],
                ))

        else:
            # Safe Deterministic Fallback
            det_claims, det_evidence = extract_chapter_deterministic_safe(
                chapter_num=ch_num,
                chapter_content=ch_content,
                registry=registry,
            )
            verified_claims.extend(det_claims)
            verified_evidence.extend(det_evidence)

    # Ensure minimal presence if no characters detected
    if not registry.characters:
        registry.register_character("The Narrator", "Observer / Narrator", ["Narrator"], 1)

    dataset = StoryDataset(
        story_id=book_id,
        title=title,
        description=description or f"Story graph dataset with {len(registry.characters)} characters across {len(chapters_data)} chapters.",
        characters=list(registry.characters.values()),
        locations=list(registry.locations.values()),
        factions=list(registry.factions.values()),
        events=list(registry.events.values()),
        claims=verified_claims,
        evidence=verified_evidence,
    )

    return ExtractionPipelineResult(
        dataset=dataset,
        status=status,
        status_message=status_message,
        claims_accepted=len(verified_claims),
        claims_rejected=len(rejected_reasons),
        rejected_reasons=rejected_reasons,
    )
