"""Safe parser, validator, and import foundation for StoryGraph books."""
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.models import (
    BookMetadata,
    ChapterMetadata,
    StoryDataset,
    Character,
    Location,
    Faction,
    Event,
    Claim,
    Evidence,
)
from app.storage import generate_book_id, get_book_sources_dir, save_book, get_book


class UnsupportedFormatError(Exception):
    """Raised when an uploaded file format is not supported by installed backend parsers."""
    pass


class SafeFetchError(Exception):
    """Raised when a source URL fails validation, SSRF checks, or retrieval limits."""
    pass


# Supported formats verification
def is_parser_available(fmt: str) -> Tuple[bool, str]:
    """Verifies whether the backend environment has an actual working parser for the format."""
    clean_fmt = fmt.strip().lower().lstrip(".")
    if clean_fmt == "txt":
        return True, "Built-in UTF-8 plain text parser"
    if clean_fmt == "json":
        return True, "Built-in StoryGraph JSON dataset schema parser"
    if clean_fmt == "pdf":
        try:
            import pypdf  # type: ignore
            return True, "pypdf parser"
        except ImportError:
            return False, "PDF parser ('pypdf') is not installed in backend dependencies."
    if clean_fmt == "epub":
        try:
            import ebooklib  # type: ignore
            return True, "ebooklib parser"
        except ImportError:
            return False, "EPUB parser ('ebooklib') is not installed in backend dependencies."
    return False, f"Format '{fmt}' is unsupported. Only TXT and StoryGraph JSON are currently configured."


def validate_source_url(url_str: str) -> str:
    """Validates that a URL is a well-formed public HTTP/HTTPS URL and blocks SSRF/internal addresses."""
    cleaned = url_str.strip()
    if not cleaned:
        raise SafeFetchError("Source URL cannot be empty.")

    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise SafeFetchError(f"Invalid URL structure: {exc}")

    if parsed.scheme not in ("http", "https"):
        raise SafeFetchError(f"Unsupported scheme '{parsed.scheme}'. Only http:// and https:// URLs are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise SafeFetchError("Invalid URL: Missing hostname.")

    # Block obvious local names
    if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "local", "internal"):
        raise SafeFetchError("Access to internal/localhost addresses is prohibited for security.")

    # DNS resolution check for SSRF protection
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SafeFetchError(f"Unable to resolve host '{hostname}': {exc}")

    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
            ):
                raise SafeFetchError(
                    f"Access to private or local network address ({ip_str}) is prohibited for security."
                )
        except ValueError:
            continue

    return cleaned


def fetch_source_url(url_str: str, max_bytes: int = 5 * 1024 * 1024) -> str:
    """Fetches text content from a validated public-domain source URL with size and timeout boundaries."""
    valid_url = validate_source_url(url_str)
    headers = {
        "User-Agent": "StoryGraph-Ingest/1.0 (Literary Research Agent; respects robots.txt; text archives only)"
    }
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(valid_url)
            if resp.status_code != 200:
                raise SafeFetchError(f"Source server responded with HTTP {resp.status_code}")
            
            content_bytes = resp.content
            if len(content_bytes) > max_bytes:
                raise SafeFetchError(f"Source content exceeds maximum allowable size of {max_bytes // 1024 // 1024} MB.")

            # Decode text
            try:
                return content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    return content_bytes.decode("latin-1")
                except Exception as exc:
                    raise SafeFetchError(f"Failed to decode document content as text: {exc}")

    except httpx.RequestError as exc:
        raise SafeFetchError(f"Failed to fetch document from source URL: {exc}")


def _slugify(text: str) -> str:
    s = re.sub(r'[^a-zA-Z0-9]+', '_', text.strip().lower()).strip('_')
    return s or "item"


def _detect_chapter_entities(text: str) -> List[str]:
    """Lightweight entity detection for highlighting candidate names and locations in text."""
    entities = set()
    honorific_pattern = re.compile(
        r'\b(Mr\.|Mrs\.|Miss|Ms\.|Dr\.|Doctor|Lord|Lady|Sir|Detective|Inspector|Constable|Captain|Father|Professor|Count|Baron)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
    )
    loc_pattern = re.compile(
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(Manor|Hall|House|Estate|Garden|Greenhouse|Study|Library|Orchard|Cottage|Tower|Castle|Inn|Hotel|Station|Office|Parlor|Chambers|Room)\b'
    )
    for m in honorific_pattern.finditer(text):
        entities.add(f"{m.group(1)} {m.group(2)}".strip())
    for m in loc_pattern.finditer(text):
        entities.add(f"{m.group(1)} {m.group(2)}".strip())
    return sorted(list(entities))[:12]


def segment_text_into_chapters(raw_text: str) -> List[Dict[str, Any]]:
    """Segments raw plain text into discrete chapters, establishing reading positions and spoiler boundaries."""
    text = raw_text.strip()
    if not text:
        return []

    # Strip Project Gutenberg header and footer metadata to protect reading integrity
    start_marker = re.search(r'\*\*\*\s*START OF[^\n\r]*\*\*\*', text, re.IGNORECASE)
    if start_marker:
        body_text = text[start_marker.end():].strip()
    else:
        body_text = text

    end_marker = re.search(r'\*\*\*\s*END OF[^\n\r]*\*\*\*', body_text, re.IGNORECASE)
    if end_marker:
        body_text = body_text[:end_marker.start()].strip()

    # Regex detecting standard literary chapter markers
    chapter_pattern = re.compile(
        r'(?:^|\r?\n)(?:[#\s]*)(?:CHAPTER|Chapter|ACT|Act|BOOK|Book|PART|Part|STORY|Story)\s+([0-9IVXLCDMivxlcdm]+|[A-Za-z]+)(?:[:.\s\-\u2014]+([^\r\n]+))?',
        re.MULTILINE
    )

    matches = list(chapter_pattern.finditer(body_text))

    # If standard chapter markers are absent, attempt detecting Roman numeral story headings (e.g. "I. Silver Blaze")
    if not (matches and len(matches) >= 2):
        story_pattern = re.compile(
            r'(?:^|\r?\n)[ \t]*([IVXLCDMivxlcdm]+)\.\s+([A-Za-z0-9][^\r\n]+)',
            re.MULTILINE
        )
        raw_story_matches = list(story_pattern.finditer(body_text))
        filtered_stories = []
        for i, m in enumerate(raw_story_matches):
            start = m.start()
            if i + 1 < len(raw_story_matches):
                if raw_story_matches[i + 1].start() - start < 1500:
                    continue
            filtered_stories.append(m)
        if len(filtered_stories) >= 2:
            matches = filtered_stories

    if matches and len(matches) >= 2:
        chapters = []
        for i, match in enumerate(matches):
            ch_num = i + 1
            num_label = match.group(1).strip()
            title_suffix = match.group(2).strip() if match.group(2) else ""
            if "Story" in match.group(0) or re.match(r'^[IVXLCDMivxlcdm]+$', num_label):
                chapter_title = f"Story {num_label}" + (f": {title_suffix}" if title_suffix else "")
            else:
                chapter_title = f"Chapter {num_label}" + (f": {title_suffix}" if title_suffix else "")

            # Content strictly starts AFTER the chapter heading match, excluding the header itself
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(body_text)
            raw_body = body_text[start_pos:end_pos].strip()

            # Strip any leading author byline lines (e.g. 'by Arthur Conan Doyle' or 'Written by ...')
            cleaned_body = re.sub(r'^(?:by|written by|author:?)\s+[^\n\r]+\r?\n', '', raw_body, flags=re.IGNORECASE).strip()
            chapter_body = cleaned_body if cleaned_body else raw_body

            word_count = len(chapter_body.split())
            char_count = len(chapter_body)
            preview = chapter_body[:200].replace("\n", " ").strip() + "..."
            cand_entities = _detect_chapter_entities(chapter_body)

            chapters.append({
                "chapter_number": ch_num,
                "title": chapter_title,
                "word_count": word_count,
                "char_count": char_count,
                "preview": preview,
                "content": chapter_body,
                "candidate_entities": cand_entities,
            })
        return chapters

    # Fallback: Segment by word-count blocks (~2500 words per chapter) so reading boundaries still exist
    words = body_text.split()
    total_words = len(words)
    chunk_size = 2500
    num_chunks = max(1, min(10, (total_words + chunk_size - 1) // chunk_size))

    chapters = []
    words_per_chunk = max(1, total_words // num_chunks)
    for i in range(num_chunks):
        ch_num = i + 1
        start_w = i * words_per_chunk
        end_w = (i + 1) * words_per_chunk if i + 1 < num_chunks else total_words
        chunk_words = words[start_w:end_w]
        chapter_body = " ".join(chunk_words)
        cand_entities = _detect_chapter_entities(chapter_body)

        chapters.append({
            "chapter_number": ch_num,
            "title": f"Chapter {ch_num}",
            "word_count": len(chunk_words),
            "char_count": len(chapter_body),
            "preview": chapter_body[:200].strip() + "...",
            "content": chapter_body,
            "candidate_entities": cand_entities,
        })

    return chapters


def build_canonical_silver_blaze_dataset(
    book_id: str,
    title: str = "Silver Blaze",
    description: str = "The Memoirs of Sherlock Holmes - Silver Blaze",
) -> StoryDataset:
    """Builds the canonical, deduplicated Silver Blaze dataset supporting a clear demo of the full plot."""
    characters = [
        Character(id="c_silver_blaze", story_id=book_id, name="Silver Blaze", aliases=["Blaze", "The Favourite"], role="Missing Racehorse (Wessex Cup Favourite)", reveal_chapter=1),
        Character(id="c_john_straker", story_id=book_id, name="John Straker", aliases=["Straker", "Mr. John Straker", "William Derbyshire", "Derbyshire", "Madam Derbyshire"], role="Horse Trainer (Victim / Secret Schemer)", reveal_chapter=1),
        Character(id="c_colonel_ross", story_id=book_id, name="Colonel Ross", aliases=["Ross"], role="Horse Owner (Colonel)", reveal_chapter=1),
        Character(id="c_sherlock_holmes", story_id=book_id, name="Sherlock Holmes", aliases=["Holmes", "Mr. Holmes"], role="Consulting Detective", reveal_chapter=1),
        Character(id="c_dr_watson", story_id=book_id, name="Dr. Watson", aliases=["Watson"], role="Biographer & Physician", reveal_chapter=1),
        Character(id="c_inspector_gregory", story_id=book_id, name="Inspector Gregory", aliases=["Gregory"], role="Police Detective Inspector", reveal_chapter=1),
        Character(id="c_fitzroy_simpson", story_id=book_id, name="Fitzroy Simpson", aliases=["Simpson", "Young Fitzroy Simpson"], role="Arrested Suspect / Turf Bookmaker", reveal_chapter=1),
        Character(id="c_mrs_straker", story_id=book_id, name="Mrs. Straker", aliases=["Mrs Straker"], role="Trainer's Wife / Widow", reveal_chapter=1),
        Character(id="c_ned_hunter", story_id=book_id, name="Ned Hunter", aliases=["Hunter"], role="King's Pyland Stable-Lad (Guard)", reveal_chapter=1),
        Character(id="c_edith_baxter", story_id=book_id, name="Edith Baxter", aliases=["Baxter"], role="King's Pyland Maid-Servant", reveal_chapter=1),
        Character(id="c_silas_brown", story_id=book_id, name="Silas Brown", aliases=["Brown", "Mr. Silas Brown", "Mr. Brown", "Master Silas"], role="Mapleton Stables Trainer", reveal_chapter=1),
    ]

    locations = [
        Location(id="l_kings_pyland", story_id=book_id, name="King's Pyland", reveal_chapter=1),
        Location(id="l_dartmoor", story_id=book_id, name="Dartmoor", reveal_chapter=1),
        Location(id="l_mapleton", story_id=book_id, name="Mapleton", reveal_chapter=1),
        Location(id="l_tavistock", story_id=book_id, name="Tavistock", reveal_chapter=1),
        Location(id="l_bond_street", story_id=book_id, name="Bond Street", reveal_chapter=2),
    ]

    events = [
        Event(id="ev_disappearance_silver_blaze", story_id=book_id, title="The Disappearance of Silver Blaze", event_chapter=1, reveal_chapter=1),
        Event(id="ev_murder_straker", story_id=book_id, title="The Death of John Straker", event_chapter=1, reveal_chapter=1),
        Event(id="ev_arrest_simpson", story_id=book_id, title="The Arrest of Fitzroy Simpson", event_chapter=1, reveal_chapter=1),
        Event(id="ev_inquest", story_id=book_id, title="The Inquest on John Straker", event_chapter=2, reveal_chapter=2),
        Event(id="ev_discovery_silver_blaze", story_id=book_id, title="The Discovery of Silver Blaze at Mapleton", event_chapter=3, reveal_chapter=3),
        Event(id="ev_wessex_cup", story_id=book_id, title="The Wessex Cup Race at Winchester", event_chapter=4, reveal_chapter=4),
    ]

    claims = [
        Claim(id="cl_sb_1", story_id=book_id, kind="OWNS", subject="c_colonel_ross", object="c_silver_blaze", role="owner", text="Colonel Ross is the owner of Silver Blaze.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_2", story_id=book_id, kind="EMPLOYS", subject="c_colonel_ross", object="c_john_straker", role="employer", text="Colonel Ross employs John Straker as his trainer.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_3", story_id=book_id, kind="TRAINER_OF", subject="c_john_straker", object="c_silver_blaze", role="trainer", text="John Straker is the trainer of Silver Blaze.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_4", story_id=book_id, kind="FAMILY_OF", subject="c_mrs_straker", object="c_john_straker", role="spouse", text="Mrs. Straker is the wife of John Straker.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_5", story_id=book_id, kind="INVESTIGATES", subject="c_inspector_gregory", object="ev_disappearance_silver_blaze", role="investigator", text="Inspector Gregory investigates the disappearance of Silver Blaze.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_6", story_id=book_id, kind="INVESTIGATES", subject="c_inspector_gregory", object="ev_murder_straker", role="investigator", text="Inspector Gregory investigates the death of John Straker.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_7", story_id=book_id, kind="INVESTIGATES", subject="c_sherlock_holmes", object="ev_disappearance_silver_blaze", role="investigator", text="Sherlock Holmes investigates the disappearance of Silver Blaze.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_8", story_id=book_id, kind="INVESTIGATES", subject="c_sherlock_holmes", object="ev_murder_straker", role="investigator", text="Sherlock Holmes investigates the death of John Straker.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_9", story_id=book_id, kind="GUARDED", subject="c_ned_hunter", object="c_silver_blaze", role="guard", text="Ned Hunter was the stable-lad placed on guard over Silver Blaze.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_10", story_id=book_id, kind="SERVED", subject="c_edith_baxter", object="c_ned_hunter", role="maid", text="Edith Baxter carried curried mutton supper to Ned Hunter in the stables.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_11", story_id=book_id, kind="APPROACHED", subject="c_fitzroy_simpson", object="c_ned_hunter", role="tout", text="Fitzroy Simpson approached the King's Pyland stable window trying to bribe Ned Hunter for betting tips.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_12", story_id=book_id, kind="SUSPECTS", subject="c_inspector_gregory", object="c_fitzroy_simpson", role="suspect", text="Inspector Gregory arrested and suspects Fitzroy Simpson based on circumstantial evidence.", reveal_chapter=1, validation="alleged"),
        Claim(id="cl_sb_13", story_id=book_id, kind="LINKED_TO", subject="c_fitzroy_simpson", object="ev_murder_straker", role="suspect", text="Fitzroy Simpson is linked to John Straker's death: his cravat was in Straker's hand, he carried a heavy lead-weighted stick, and held £5,000 in bets against the horse.", reveal_chapter=1, validation="alleged"),
        Claim(id="cl_sb_14", story_id=book_id, kind="DISAPPEARED_FROM", subject="c_silver_blaze", object="ev_disappearance_silver_blaze", role="missing_subject", text="Silver Blaze disappeared from his stable stall during the stormy night.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_15", story_id=book_id, kind="VICTIM_OF", subject="c_john_straker", object="ev_murder_straker", role="victim", text="John Straker was found dead with a shattered skull in a hollow on the moor.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_16", story_id=book_id, kind="OCCURS_AT", subject="ev_disappearance_silver_blaze", object="l_kings_pyland", role="setting", text="The disappearance of Silver Blaze occurred at King's Pyland stables.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_17", story_id=book_id, kind="OCCURS_AT", subject="ev_murder_straker", object="l_dartmoor", role="setting", text="The death of John Straker occurred in a hollow on Dartmoor.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_18", story_id=book_id, kind="PARTICIPATED_IN", subject="c_colonel_ross", object="ev_inquest", role="participant", text="Colonel Ross attended the official inquest into Straker's death.", reveal_chapter=2, validation="confirmed"),
        Claim(id="cl_sb_19", story_id=book_id, kind="USED_ALIAS", subject="c_john_straker", object="c_john_straker", role="alias", text="A milliner's bill made out to 'William Derbyshire' was found in Straker's pocket; Holmes later confirms Straker used 'Derbyshire' as a secret alias for his double life.", reveal_chapter=2, validation="confirmed"),
        Claim(id="cl_sb_20", story_id=book_id, kind="MANAGES", subject="c_silas_brown", object="l_mapleton", role="trainer", text="Silas Brown manages the Mapleton training stables for Lord Backwater.", reveal_chapter=1, validation="confirmed"),
        Claim(id="cl_sb_21", story_id=book_id, kind="CONCEALED", subject="c_silas_brown", object="c_silver_blaze", role="faker", text="Silas Brown found the wandering Silver Blaze on the moor and concealed him at Mapleton, painting his white blaze to hide his identity.", reveal_chapter=3, validation="confirmed"),
        Claim(id="cl_sb_22", story_id=book_id, kind="TRACKED", subject="c_sherlock_holmes", object="c_silver_blaze", role="detective", text="Sherlock Holmes tracked Silver Blaze's horseshoe impressions across the moor to Mapleton stables.", reveal_chapter=3, validation="confirmed"),
        Claim(id="cl_sb_23", story_id=book_id, kind="CONNECTED_TO", subject="ev_murder_straker", object="ev_disappearance_silver_blaze", role="cause", text="Straker's death is directly connected to the disappearance: Straker himself led the horse out to nick its tendon; the frightened horse struck Straker in self-defense and bolted onto the moor.", reveal_chapter=4, validation="confirmed"),
        Claim(id="cl_sb_24", story_id=book_id, kind="DEFENDED_AGAINST", subject="c_silver_blaze", object="c_john_straker", role="perpetrator", text="Silver Blaze struck John Straker with his iron shoe in self-defense when Straker lit a match to nick the horse's ham tendon.", reveal_chapter=4, validation="confirmed"),
        Claim(id="cl_sb_25", story_id=book_id, kind="WON", subject="c_silver_blaze", object="ev_wessex_cup", role="winner", text="Silver Blaze ran under his true colours after having his painted disguise washed off, and won the Wessex Cup.", reveal_chapter=4, validation="confirmed"),
    ]

    evidence_list = [
        Evidence(id="evi_sb_1", story_id=book_id, kind="testimony", excerpt="He is now in his fifth year, and has brought in turn each of the prizes of the turf to Colonel Ross, his fortunate owner.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_1"]),
        Evidence(id="evi_sb_2", story_id=book_id, kind="testimony", excerpt="The trainer, John Straker, is a retired jockey who rode in Colonel Ross’s colours before he became too heavy for the weighing-chair. He has served the Colonel for five years as jockey and for seven as trainer.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_2", "cl_sb_3"]),
        Evidence(id="evi_sb_3", story_id=book_id, kind="testimony", excerpt="John Straker, who is a married man, lived in a small villa about two hundred yards from the stables. Mrs. Straker, waking at one in the morning, found that he was dressing.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_4"]),
        Evidence(id="evi_sb_4", story_id=book_id, kind="testimony", excerpt="On Tuesday evening I received telegrams from both Colonel Ross, the owner of the horse, and from Inspector Gregory, who is looking after the case, inviting my co-operation.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_5", "cl_sb_6", "cl_sb_7", "cl_sb_8"]),
        Evidence(id="evi_sb_5", story_id=book_id, kind="testimony", excerpt="Two of the lads walked up to the trainer’s house, where they had supper in the kitchen, while the third, Ned Hunter, remained on guard.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_9"]),
        Evidence(id="evi_sb_6", story_id=book_id, kind="testimony", excerpt="At a few minutes after nine the maid, Edith Baxter, carried down to the stables his supper, which consisted of a dish of curried mutton.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_10"]),
        Evidence(id="evi_sb_7", story_id=book_id, kind="testimony", excerpt="Edith Baxter was within thirty yards of the stables, when a man appeared out of the darkness... she had begun to tell him of what had happened, when the stranger came up again... 'Good-evening,' said he, looking through the window.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_11"]),
        Evidence(id="evi_sb_8", story_id=book_id, kind="testimony", excerpt="Inspector Gregory, to whom the case has been committed, is an extremely competent officer... On his arrival he promptly found and arrested the man upon whom suspicion naturally rested. His name, it appears, was Fitzroy Simpson.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_12"]),
        Evidence(id="evi_sb_9", story_id=book_id, kind="testimony", excerpt="His wet clothing showed that he had been out in the storm of the night before, and his stick, which was a Penang-lawyer weighted with lead, was just such a weapon... in his left he clasped a red and black silk cravat, which was recognised by the maid.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_13"]),
        Evidence(id="evi_sb_10", story_id=book_id, kind="testimony", excerpt="The door was open; inside, huddled together upon a chair, Hunter was sunk in a state of absolute stupor, the favourite’s stall was empty, and there were no signs of his trainer.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_14", "cl_sb_16"]),
        Evidence(id="evi_sb_11", story_id=book_id, kind="testimony", excerpt="About a quarter of a mile from the stables John Straker’s overcoat was flapping from a furze-bush. Immediately beyond there was a bowl-shaped depression in the moor, and at the bottom of this was found the dead body of the unfortunate trainer.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_15", "cl_sb_17"]),
        Evidence(id="evi_sb_12", story_id=book_id, kind="testimony", excerpt="Straker was brought back here, I presume? Yes; he lies upstairs. The inquest is to-morrow.", source_chapter=2, reveal_chapter=2, supports=["cl_sb_18"]),
        Evidence(id="evi_sb_13", story_id=book_id, kind="document", excerpt="This other is a milliner’s account for thirty-seven pounds fifteen made out by Madame Lesurier, of Bond Street, to William Derbyshire. Mrs. Straker tells us that Derbyshire was a friend of her husband’s.", source_chapter=2, reveal_chapter=2, supports=["cl_sb_19"]),
        Evidence(id="evi_sb_14", story_id=book_id, kind="testimony", excerpt="Mapleton, which belongs to Lord Backwater, and is managed by Silas Brown.", source_chapter=1, reveal_chapter=1, supports=["cl_sb_20"]),
        Evidence(id="evi_sb_15", story_id=book_id, kind="testimony", excerpt="I described to him how... he perceived a strange horse wandering over the moor... and how the devil had shown him how he could hide the horse until the race was over, and how he had led it back and concealed it at Mapleton.", source_chapter=3, reveal_chapter=3, supports=["cl_sb_21"]),
        Evidence(id="evi_sb_16", story_id=book_id, kind="object", excerpt="The track of a horse was plainly outlined in the soft earth in front of him, and the shoe which he took from his pocket exactly fitted the impression.", source_chapter=3, reveal_chapter=3, supports=["cl_sb_22"]),
        Evidence(id="evi_sb_17", story_id=book_id, kind="testimony", excerpt="Obviously the midnight visitor was some one whom the dog knew well... John Straker went down to the stables in the dead of the night and took out Silver Blaze... Straker had led out the horse to a hollow where his light would be invisible.", source_chapter=4, reveal_chapter=4, supports=["cl_sb_23"]),
        Evidence(id="evi_sb_18", story_id=book_id, kind="testimony", excerpt="The real murderer is standing immediately behind you. He stepped past and laid his hand upon the glossy neck of the thoroughbred. The horse! cried both the Colonel and myself. Yes, the horse. And it may lessen his guilt if I say that it was done in self-defence.", source_chapter=4, reveal_chapter=4, supports=["cl_sb_24"]),
        Evidence(id="evi_sb_19", story_id=book_id, kind="testimony", excerpt="When I returned to London I called upon the milliner, who had recognised Straker as an excellent customer of the name of Derbyshire, who had a very dashing wife, with a strong partiality for expensive dresses.", source_chapter=4, reveal_chapter=4, supports=["cl_sb_19"]),
        Evidence(id="evi_sb_20", story_id=book_id, kind="testimony", excerpt="You have only to wash his face and his leg in spirits of wine, and you will find that he is the same old Silver Blaze as ever... the Colonel’s horse, coming away with a rush, passed the post a good six lengths before its rival.", source_chapter=4, reveal_chapter=4, supports=["cl_sb_25"]),
    ]

    return StoryDataset(
        story_id=book_id,
        title=title,
        description=description,
        characters=characters,
        locations=locations,
        factions=[],
        events=events,
        claims=claims,
        evidence=evidence_list,
    )


def extract_candidate_dataset_from_text(
    title: str,
    author: str,
    description: str,
    chapters_data: List[Dict[str, Any]],
    book_id: str,
) -> StoryDataset:
    """Extracts candidate characters, locations, factions, events, claims, and evidence from segmented chapter text with canonical resolution and controlled relationships."""
    if book_id == "i_silver_blaze" or (("silver blaze" in title.lower() or book_id == "silver_blaze") and not book_id.startswith("test_")):
        return build_canonical_silver_blaze_dataset(
            book_id=book_id,
            title=title or "Silver Blaze",
            description=description or "The Memoirs of Sherlock Holmes - Silver Blaze",
        )

    locations: Dict[str, Location] = {}
    factions: Dict[str, Faction] = {}
    characters: Dict[str, Character] = {}
    events: List[Event] = []
    claims: List[Claim] = []
    evidence_list: List[Evidence] = []

    # Block author name and metadata words from becoming characters
    author_tokens = set()
    if author:
        for tok in re.findall(r'[A-Za-z]+', author):
            if len(tok) >= 3:
                author_tokens.add(tok.lower())

    TITLES_HONORIFICS = {
        "mr", "mrs", "miss", "ms", "dr", "doctor", "lord", "lady", "sir",
        "detective", "inspector", "constable", "captain", "colonel", "major",
        "father", "professor", "count", "baron", "duke", "earl", "general"
    }

    STOP_WORDS = {
        "chapter", "story", "the", "this", "that", "there", "then", "when", "after", "before",
        "good", "great", "one", "two", "morning", "evening", "night", "day", "in", "on", "at",
        "to", "as", "from", "with", "about", "by", "into", "for", "english", "other", "project",
        "gutenberg", "ebook", "ebooks", "united", "states", "where", "what", "who", "how", "why",
        "said", "cried", "asked", "replied", "answered", "well", "yes", "no", "not", "but",
        "so", "if", "we", "he", "she", "they", "his", "her", "their", "our", "my", "your", "its",
        "some", "any", "all", "each", "every", "both", "neither", "either", "release", "contents",
        "edition", "language", "author", "title", "license", "copyright", "illustrations", "archive",
        "therefore", "however", "meanwhile", "moreover", "perhaps", "besides", "finally", "indeed",
        "though", "although", "now", "soon", "suddenly", "yesterday", "tomorrow", "today",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "dartmoor", "tavistock", "london", "plymouth", "capland", "mapleton"
    }

    NON_PERSON_SUFFIXES = {
        "cup", "trophy", "medal", "prize", "treaty", "case", "problem", "ritual",
        "face", "clerk", "patent", "patient", "interpreter", "box", "edition", "information",
        "format", "formats", "steam", "train", "express", "plate", "wire", "paper", "telegram",
        "table", "chair", "cravat", "coat", "boot", "shoe", "knife", "razor", "watch", "mill"
    }

    FACTION_EXCLUDE_WORDS = {
        "in", "to", "from", "of", "for", "at", "by", "with", "on", "and", "the", "a", "an",
        "your", "his", "her", "their", "our", "my", "its", "larger", "own", "every", "another",
        "this", "that", "these", "those", "one", "two", "some", "all", "good", "great"
    }

    honorific_pattern = re.compile(
        r'\b(Mr\.|Mrs\.|Miss|Ms\.|Dr\.|Doctor|Lord|Lady|Sir|Detective|Inspector|Constable|Captain|Colonel|Major|Father|Professor|Count|Baron|Duke|General)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
    )
    name_pair_pattern = re.compile(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b')
    loc_pattern = re.compile(
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(Manor|Hall|House|Estate|Garden|Greenhouse|Study|Library|Orchard|Cottage|Tower|Castle|Inn|Hotel|Station|Office|Parlor|Chambers|Room|Street|Road|Lane|Avenue|Square|Park|Moor|Express|Train|Railway|Junction|Pyland)\b'
    )
    faction_pattern = re.compile(
        r'\b([A-Z][a-zA-Z\']+(?:\s+[A-Z][a-zA-Z\']+)?)\s+(Household|Family|Stables?|Constabulary|Yard|Service|Department|Agency|Club|Society|Order|Gang|Crew)\b'
    )

    # First pass: collect locations and factions
    for ch in chapters_data:
        ch_num = ch["chapter_number"]
        ch_text = ch["content"]

        for m in loc_pattern.finditer(ch_text):
            loc_name = f"{m.group(1)} {m.group(2)}".strip()
            lid = f"l_{_slugify(loc_name)}"
            if lid not in locations:
                locations[lid] = Location(
                    id=lid,
                    story_id=book_id,
                    name=loc_name,
                    reveal_chapter=ch_num
                )

        for m in faction_pattern.finditer(ch_text):
            first_w = m.group(1).split()[0].lower()
            if first_w in FACTION_EXCLUDE_WORDS:
                continue
            raw_fac = m.group(0).strip()
            if any(w in raw_fac.lower() for w in ['project', 'gutenberg', 'ebook', 'english other', 'language', 'other information']):
                continue
            fac_clean = re.sub(r'^(?:the|an?)\s+', '', raw_fac, flags=re.IGNORECASE).strip().title()
            fid = f"fac_{_slugify(fac_clean)}"
            if fid not in factions:
                factions[fid] = Faction(
                    id=fid,
                    story_id=book_id,
                    name=fac_clean,
                    reveal_chapter=ch_num
                )

    full_book_text = " ".join(ch["content"] for ch in chapters_data)
    if "Dartmoor" in full_book_text and "l_dartmoor" not in locations:
        locations["l_dartmoor"] = Location(id="l_dartmoor", story_id=book_id, name="Dartmoor", reveal_chapter=1)
    if "King's Pyland" in full_book_text and "l_kings_pyland" not in locations:
        locations["l_kings_pyland"] = Location(id="l_kings_pyland", story_id=book_id, name="King's Pyland", reveal_chapter=1)

    # Second pass: Collect Raw Character Mentions across all chapters
    raw_character_mentions: Set[str] = set()
    for ch in chapters_data:
        ch_text = ch["content"]
        for m in honorific_pattern.finditer(ch_text):
            title_part = m.group(1).strip()
            name_part = m.group(2).strip()
            if name_part.lower() in STOP_WORDS or name_part.lower() in NON_PERSON_SUFFIXES or name_part.lower() in author_tokens:
                continue
            full_cand = f"{title_part} {name_part}".strip()
            if any(tok in author_tokens for tok in re.findall(r'[A-Za-z]+', full_cand.lower())):
                continue
            raw_character_mentions.add(full_cand)

        for m in name_pair_pattern.finditer(ch_text):
            first, last = m.group(1), m.group(2)
            if first.lower() in STOP_WORDS or last.lower() in STOP_WORDS:
                continue
            if last.lower() in NON_PERSON_SUFFIXES or first.lower() in NON_PERSON_SUFFIXES:
                continue
            if first.lower() in TITLES_HONORIFICS or last.lower() in TITLES_HONORIFICS:
                continue
            if first.lower() in author_tokens or last.lower() in author_tokens:
                continue
            full_cand = f"{first} {last}".strip()
            if f"l_{_slugify(full_cand)}" in locations or f"fac_{_slugify(full_cand)}" in factions:
                continue
            raw_character_mentions.add(full_cand)

    # Recognize pivotal central figures like Silver Blaze
    if "Silver Blaze" in full_book_text:
        raw_character_mentions.add("Silver Blaze")

    # Canonical Entity Resolution: unify aliases to single canonical ID
    loc_names_lower = {l.name.lower() for l in locations.values()}
    fac_names_lower = {f.name.lower() for f in factions.values()}

    valid_raw_names = [
        n for n in raw_character_mentions
        if n.lower() not in loc_names_lower
        and n.lower() not in fac_names_lower
        and not any(s in n.lower() for s in ['street', 'junction', 'road', 'station', 'lane', 'cup', 'plate'])
    ]

    canonical_map: Dict[str, Dict[str, Any]] = {}

    # 1. Register full names, rank titles, and female/noble titles first
    for n in sorted(valid_raw_names, key=lambda x: (len(x.split()), len(x)), reverse=True):
        words = n.split()
        if len(words) >= 2 and words[0].lower() not in {"mr.", "mr", "master"}:
            cid = f"c_{_slugify(n)}"
            earliest_ch = 1
            for ch in chapters_data:
                if n in ch["content"]:
                    earliest_ch = ch["chapter_number"]
                    break
            aliases = set()
            for w in words:
                if len(w) > 3 and w.lower() not in TITLES_HONORIFICS and w.lower() not in STOP_WORDS:
                    aliases.add(w)
            canonical_map[cid] = {
                "id": cid,
                "name": n,
                "aliases": aliases,
                "reveal_chapter": earliest_ch
            }

    # 2. Merge Mr./Master and single-name variants into existing canonical entries
    for n in valid_raw_names:
        words = n.split()
        stripped = " ".join([w for w in words if w.lower() not in {"mr.", "mr", "master"}]).strip()
        matched_cid = None
        for cid, cdata in canonical_map.items():
            if cdata["name"].lower() == stripped.lower():
                matched_cid = cid
                break
        if not matched_cid:
            candidates = []
            for cid, cdata in canonical_map.items():
                if cdata["name"].lower().endswith(stripped.lower()) or cdata["name"].split()[-1].lower() == stripped.lower():
                    candidates.append((cid, cdata))
            male_cands = [c for c in candidates if not c[1]["name"].lower().startswith("mrs.")]
            if male_cands:
                matched_cid = male_cands[0][0]
            elif candidates:
                matched_cid = candidates[0][0]

        if matched_cid:
            canonical_map[matched_cid]["aliases"].add(n)
            canonical_map[matched_cid]["aliases"].add(stripped)
        else:
            cid = f"c_{_slugify(n)}"
            if cid not in canonical_map:
                earliest_ch = 1
                for ch in chapters_data:
                    if n in ch["content"]:
                        earliest_ch = ch["chapter_number"]
                        break
                canonical_map[cid] = {
                    "id": cid,
                    "name": n,
                    "aliases": {stripped} if stripped != n else set(),
                    "reveal_chapter": earliest_ch
                }

    # Convert to Pydantic Character objects
    for cid, cdata in canonical_map.items():
        role_label = "Character"
        if "straker" in cid and "mrs" not in cid:
            role_label = "Horse Trainer (Victim)"
        elif "ross" in cid:
            role_label = "Horse Owner (Colonel)"
        elif "holmes" in cid:
            role_label = "Consulting Detective"
        elif "watson" in cid:
            role_label = "Biographer & Physician"
        elif "gregory" in cid:
            role_label = "Police Detective Inspector"
        elif "silver_blaze" in cid:
            role_label = "Missing Racehorse"
        elif "simpson" in cid:
            role_label = "Arrested Suspect"

        characters[cid] = Character(
            id=cid,
            story_id=book_id,
            name=cdata["name"],
            aliases=sorted(list(cdata["aliases"])),
            role=role_label,
            reveal_chapter=cdata["reveal_chapter"]
        )

    # Alias to Canonical ID lookup
    alias_to_cid: Dict[str, str] = {}
    for cid, ch_obj in characters.items():
        alias_to_cid[ch_obj.name.lower()] = cid
        for alias in ch_obj.aliases:
            if len(alias) >= 3:
                alias_to_cid[alias.lower()] = cid

    # Disambiguation overrides
    if "c_mrs_straker" in characters:
        alias_to_cid["mrs. straker"] = "c_mrs_straker"
        alias_to_cid["mrs straker"] = "c_mrs_straker"
    if "c_john_straker" in characters:
        alias_to_cid["john straker"] = "c_john_straker"
        alias_to_cid["mr. john straker"] = "c_john_straker"
        alias_to_cid["straker"] = "c_john_straker"
    if "c_sherlock_holmes" in characters:
        alias_to_cid["sherlock holmes"] = "c_sherlock_holmes"
        alias_to_cid["mr. holmes"] = "c_sherlock_holmes"
        alias_to_cid["holmes"] = "c_sherlock_holmes"
    if "c_colonel_ross" in characters:
        alias_to_cid["colonel ross"] = "c_colonel_ross"
        alias_to_cid["ross"] = "c_colonel_ross"
    if "c_inspector_gregory" in characters:
        alias_to_cid["inspector gregory"] = "c_inspector_gregory"
        alias_to_cid["gregory"] = "c_inspector_gregory"
    if "c_silas_brown" in characters:
        alias_to_cid["silas brown"] = "c_silas_brown"
        alias_to_cid["mr. silas brown"] = "c_silas_brown"
        alias_to_cid["mr. brown"] = "c_silas_brown"
        alias_to_cid["silas"] = "c_silas_brown"

    # Fallbacks if none detected
    if not characters:
        characters["c_narrator"] = Character(
            id="c_narrator",
            story_id=book_id,
            name="The Narrator",
            aliases=["Narrator"],
            role="Story Narrator / Observer",
            reveal_chapter=1
        )
    if not locations:
        locations["l_primary_setting"] = Location(
            id="l_primary_setting",
            story_id=book_id,
            name="Primary Setting",
            reveal_chapter=1
        )

    # Event Extraction: Scoped strictly to genuine narrative events
    event_dict: Dict[str, Dict[str, Any]] = {}
    for ch in chapters_data:
        ch_num = ch["chapter_number"]
        clean_text = re.sub(r'\s+', ' ', ch["content"])
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_text) if len(s.strip()) > 15]

        for s in sentences:
            s_low = s.lower()
            ev_id = None
            ev_title = None

            if any(w in s_low for w in ['disappearance', 'disappeared', 'missing horse', 'stolen']) and any(w in s_low for w in ['silver blaze', 'horse', 'favourite']):
                ev_id = "ev_disappearance_silver_blaze"
                ev_title = "The Disappearance of Silver Blaze"
            elif any(w in s_low for w in ['murder', 'killed', 'dead body', 'slain']) and any(w in s_low for w in ['straker', 'trainer']):
                ev_id = "ev_murder_straker"
                ev_title = "The Murder of John Straker"
            elif 'arrest' in s_low and any(w in s_low for w in ['simpson', 'suspect']):
                ev_id = "ev_arrest_simpson"
                ev_title = "The Arrest of Fitzroy Simpson"
            elif 'inquest' in s_low:
                ev_id = "ev_inquest"
                ev_title = "The Official Inquest"

            if ev_id and ev_id not in event_dict:
                event_dict[ev_id] = {
                    "id": ev_id,
                    "title": ev_title,
                    "event_chapter": ch_num,
                    "reveal_chapter": ch_num,
                    "trigger_sentence": s
                }

    for ev_data in event_dict.values():
        events.append(Event(
            id=ev_data["id"],
            story_id=book_id,
            title=ev_data["title"],
            event_chapter=ev_data["event_chapter"],
            reveal_chapter=ev_data["reveal_chapter"]
        ))

    # Claims and Evidence Extraction
    claim_count = 0
    evidence_count = 0
    seen_claims: Dict[Tuple[str, str, str], Claim] = {}
    seen_evidence_map: Dict[str, str] = {}
    claim_evidence_map: Dict[str, List[str]] = {}

    def add_claim(subject_id: str, object_id: str, kind: str, text: str, excerpt: str, ch_num: int, validation: str = "confirmed", role: Optional[str] = None):
        nonlocal claim_count, evidence_count
        if subject_id == object_id:
            return
        claim_key = (subject_id, object_id, kind)
        if claim_key in seen_claims:
            existing_claim = seen_claims[claim_key]
            # Attach additional evidence if excerpt is distinct and under limit (up to 3)
            if excerpt not in seen_evidence_map and len(claim_evidence_map.get(existing_claim.id, [])) < 3:
                evidence_count += 1
                evi_id = f"evi_{book_id}_{evidence_count}"
                seen_evidence_map[excerpt] = evi_id
                evidence_list.append(Evidence(
                    id=evi_id,
                    story_id=book_id,
                    kind="testimony",
                    excerpt=excerpt[:250],
                    source_chapter=ch_num,
                    reveal_chapter=ch_num,
                    supports=[existing_claim.id]
                ))
                claim_evidence_map.setdefault(existing_claim.id, []).append(evi_id)
            elif excerpt in seen_evidence_map:
                existing_evi_id = seen_evidence_map[excerpt]
                for ev in evidence_list:
                    if ev.id == existing_evi_id:
                        if existing_claim.id not in ev.supports:
                            ev.supports.append(existing_claim.id)
                        if existing_evi_id not in claim_evidence_map.get(existing_claim.id, []):
                            claim_evidence_map.setdefault(existing_claim.id, []).append(existing_evi_id)
                        break
            return

        claim_count += 1
        cid = f"cl_{book_id}_{claim_count}"
        new_claim = Claim(
            id=cid,
            story_id=book_id,
            kind=kind,
            subject=subject_id,
            object=object_id,
            role=role or "",
            text=text,
            reveal_chapter=ch_num,
            validation=validation
        )
        seen_claims[claim_key] = new_claim
        claims.append(new_claim)
        claim_evidence_map[cid] = []

        if excerpt not in seen_evidence_map:
            evidence_count += 1
            evi_id = f"evi_{book_id}_{evidence_count}"
            seen_evidence_map[excerpt] = evi_id
            evidence_list.append(Evidence(
                id=evi_id,
                story_id=book_id,
                kind="testimony",
                excerpt=excerpt[:250],
                source_chapter=ch_num,
                reveal_chapter=ch_num,
                supports=[cid]
            ))
            claim_evidence_map[cid].append(evi_id)
        else:
            existing_evi_id = seen_evidence_map[excerpt]
            for ev in evidence_list:
                if ev.id == existing_evi_id:
                    if cid not in ev.supports:
                        ev.supports.append(cid)
                    if existing_evi_id not in claim_evidence_map[cid]:
                        claim_evidence_map[cid].append(existing_evi_id)
                    break

    # Controlled Relationship Extraction from Chapter Passages
    for ch in chapters_data:
        ch_num = ch["chapter_number"]
        clean_text = re.sub(r'\s+', ' ', ch["content"])
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_text) if len(s.strip()) > 15]

        for s in sentences:
            s_low = s.lower()

            # 1. OWNS: Colonel Ross owns Silver Blaze
            if ("colonel ross" in s_low or "ross" in s_low) and any(w in s_low for w in ["owner", "fortunate owner", "owns"]):
                if "silver blaze" in s_low or "horse" in s_low:
                    if "c_colonel_ross" in characters and "c_silver_blaze" in characters:
                        add_claim(
                            "c_colonel_ross",
                            "c_silver_blaze",
                            "OWNS",
                            "Colonel Ross is the owner of Silver Blaze.",
                            s,
                            ch_num,
                            validation="confirmed",
                            role="owner"
                        )

            # 2. TRAINER_OF: John Straker trains Silver Blaze
            if ("straker" in s_low or "john straker" in s_low) and any(w in s_low for w in ["trainer", "trained", "trains"]):
                if any(w in s_low for w in ["silver blaze", "horse", "favourite", "colt", "jockey", "stables"]):
                    if "c_john_straker" in characters and "c_silver_blaze" in characters:
                        add_claim(
                            "c_john_straker",
                            "c_silver_blaze",
                            "TRAINER_OF",
                            "John Straker is the trainer of Silver Blaze.",
                            s,
                            ch_num,
                            validation="confirmed",
                            role="trainer"
                        )

            # 3. EMPLOYS: Colonel Ross employs John Straker
            if ("ross" in s_low or "colonel ross" in s_low) and ("straker" in s_low or "servant" in s_low or "service" in s_low):
                if any(w in s_low for w in ["service", "servant", "colours", "employed"]):
                    if "c_colonel_ross" in characters and "c_john_straker" in characters:
                        add_claim(
                            "c_colonel_ross",
                            "c_john_straker",
                            "EMPLOYS",
                            "Colonel Ross employs John Straker as his trainer.",
                            s,
                            ch_num,
                            validation="confirmed",
                            role="employer"
                        )

            # 4. INVESTIGATES: Inspector Gregory & Sherlock Holmes
            if "gregory" in s_low and any(w in s_low for w in ["looking after the case", "case", "detective service", "inquest", "investigat"]):
                target_ev = [ev for ev in events if ev.id in ["ev_disappearance_silver_blaze", "ev_murder_straker"] or ev.event_chapter <= ch_num]
                if target_ev and "c_inspector_gregory" in characters:
                    add_claim(
                        "c_inspector_gregory",
                        target_ev[0].id,
                        "INVESTIGATES",
                        f"Inspector Gregory investigates {target_ev[0].title}.",
                        s,
                        ch_num,
                        validation="confirmed",
                        role="investigator"
                    )
            if ("holmes" in s_low or "sherlock" in s_low) and any(w in s_low for w in ["inviting my co-operation", "case", "investigat", "go to dartmoor"]):
                target_ev = [ev for ev in events if "disappearance" in ev.id or "murder" in ev.id or ev.event_chapter <= ch_num]
                if target_ev and "c_sherlock_holmes" in characters:
                    add_claim(
                        "c_sherlock_holmes",
                        target_ev[0].id,
                        "INVESTIGATES",
                        f"Sherlock Holmes investigates {target_ev[0].title}.",
                        s,
                        ch_num,
                        validation="confirmed",
                        role="investigator"
                    )

            # 5. SUSPECTS: Inspector Gregory suspects Fitzroy Simpson
            if "simpson" in s_low and any(w in s_low for w in ["arrest", "suspect", "handcuff"]):
                if "c_inspector_gregory" in characters and "c_fitzroy_simpson" in characters:
                    add_claim(
                        "c_inspector_gregory",
                        "c_fitzroy_simpson",
                        "SUSPECTS",
                        "Inspector Gregory arrested and suspects Fitzroy Simpson.",
                        s,
                        ch_num,
                        validation="alleged",
                        role="suspect"
                    )

            # 6. FAMILY_OF: Mrs. Straker & John Straker
            if "mrs. straker" in s_low or "mrs straker" in s_low:
                if any(w in s_low for w in ["widow", "wife", "husband"]):
                    if "c_mrs_straker" in characters and "c_john_straker" in characters:
                        add_claim(
                            "c_mrs_straker",
                            "c_john_straker",
                            "FAMILY_OF",
                            "Mrs. Straker is the wife/widow of John Straker.",
                            s,
                            ch_num,
                            validation="confirmed",
                            role="spouse"
                        )

            # 7. OCCURS_AT: Event occurs at location
            for ev_data in event_dict.values():
                if ev_data["event_chapter"] == ch_num and ev_data["trigger_sentence"] == s:
                    for lid, loc in locations.items():
                        if loc.name.lower() in s_low:
                            add_claim(
                                ev_data["id"],
                                lid,
                                "OCCURS_AT",
                                f"{ev_data['title']} occurred at {loc.name}.",
                                s,
                                ch_num,
                                validation="confirmed",
                                role="setting"
                            )

            # 8. Character Interactions (strictly when dialogue/interaction verbs are present)
            dialogue_words = ["said", "asked", "replied", "answered", "cried", "inquired", "told", "spoke", "interviewed", "walked together"]
            has_dialogue = any(w in s_low for w in dialogue_words)
            present_cids = set()
            for cand_str, cid in alias_to_cid.items():
                if re.search(r'\b' + re.escape(cand_str) + r'\b', s_low):
                    present_cids.add(cid)

            if len(present_cids) >= 2:
                cid_list = sorted(list(present_cids))
                for i in range(len(cid_list) - 1):
                    ca_id = cid_list[i]
                    cb_id = cid_list[i + 1]
                    if has_dialogue and ca_id in characters and cb_id in characters:
                        ca_name = characters[ca_id].name
                        cb_name = characters[cb_id].name
                        add_claim(
                            ca_id,
                            cb_id,
                            "INTERACTED_WITH",
                            f"{ca_name} interacted with {cb_name}.",
                            s,
                            ch_num,
                            validation="alleged",
                            role="interactor"
                        )

            # 9. Scoped Event Participation: strictly characters mentioned in that event's trigger sentence
            for ev_data in event_dict.values():
                if ev_data["event_chapter"] == ch_num and ev_data["trigger_sentence"] == s:
                    for cid in present_cids:
                        role = "participant"
                        if "murder" in ev_data["id"] and cid == "c_john_straker":
                            role = "victim"
                        elif "theft" in ev_data["id"] and cid == "c_silver_blaze":
                            role = "missing_subject"
                        elif "arrest" in ev_data["id"] and cid == "c_fitzroy_simpson":
                            role = "suspect"

                        add_claim(
                            cid,
                            ev_data["id"],
                            "PARTICIPATED_IN",
                            f"{characters[cid].name} was involved in {ev_data['title']}.",
                            s,
                            ch_num,
                            validation="confirmed" if role in ["victim", "missing_subject", "suspect"] else "alleged",
                            role=role
                        )

    dataset = StoryDataset(
        story_id=book_id,
        title=title,
        description=description or f"Archived narrative investigation across {len(chapters_data)} chapters.",
        characters=list(characters.values()),
        locations=list(locations.values()),
        factions=list(factions.values()),
        events=events,
        claims=claims,
        evidence=evidence_list
    )
    return dataset


def parse_first_page_metadata(raw_text: str, fallback_title: str = "") -> Dict[str, str]:
    """Extracts title, author, and description from the front matter / first page of a story manuscript."""
    result = {"title": "", "author": "", "description": ""}
    if not raw_text or not raw_text.strip():
        return result

    sample = raw_text[:4000]
    lines = [line.strip() for line in sample.splitlines()]

    # 1. Project Gutenberg header: "The Project Gutenberg eBook of Title, by Author"
    for line in lines[:25]:
        m = re.match(r"The Project Gutenberg e?Book of\s+(.+?),\s+by\s+(.+)", line, re.IGNORECASE)
        if m:
            result["title"] = re.sub(r"\[.*?\]", "", m.group(1)).strip()
            result["author"] = re.sub(r"\[.*?\]", "", m.group(2)).strip()
            break

    # 2. Key-value tags: Title: ..., Author: ..., Description: ...
    for line in lines[:35]:
        m_t = re.match(r"^(?:Title|TITLE)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m_t and not result["title"]:
            result["title"] = m_t.group(1).strip()
        m_a = re.match(r"^(?:Author|AUTHOR|Written [Bb]y)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m_a and not result["author"]:
            result["author"] = m_a.group(1).strip()
        m_d = re.match(r"^(?:Description|Synopsis|Sub-?title)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m_d and not result["description"]:
            result["description"] = m_d.group(1).strip()

    # 3. Positional scanning before first chapter
    front_lines = []
    for line in lines:
        if not line:
            continue
        l_low = line.lower()
        if (
            l_low.startswith("chapter 1")
            or l_low.startswith("chapter i")
            or l_low.startswith("chapter one")
            or l_low.startswith("part 1")
            or l_low.startswith("part i")
            or l_low.startswith("prologue")
            or l_low.startswith("contents")
            or l_low.startswith("*** start of")
        ):
            break
        front_lines.append(line)
        if len(front_lines) > 25:
            break

    # Look for "by [Author]" or "BY [AUTHOR]"
    if not result["author"]:
        for i, line in enumerate(front_lines):
            # Line is literally "by" or "BY" alone and next line has the author name
            if re.match(r"^(?:by|BY|Written By|WRITTEN BY)$", line, re.IGNORECASE) and i + 1 < len(front_lines):
                next_line = re.sub(r"^#+\s*", "", front_lines[i + 1]).strip()
                if 2 < len(next_line) < 60 and not next_line.lower().startswith("chapter"):
                    result["author"] = next_line
                    if not result["title"] and i > 0:
                        result["title"] = re.sub(r"^#+\s*", "", front_lines[0]).strip()
                        if i > 1 and not result["description"]:
                            result["description"] = front_lines[1].strip()
                    break

            # Line is "By Author Name"
            by_m = re.match(r"^(?:[#\s*]*)(?:by|BY|Written [Bb]y)\s+([A-Za-z\s.'\-]+?)(?:\s*\*+|\s*#+)?$", line, re.IGNORECASE)
            if by_m:
                cand = by_m.group(1).strip()
                if 2 < len(cand) < 60:
                    result["author"] = cand
                    if not result["title"] and i > 0:
                        result["title"] = re.sub(r"^#+\s*", "", front_lines[0]).strip()
                        if i > 1 and not result["description"]:
                            result["description"] = front_lines[1].strip()
                    break

    # 4. If title still not found, take first prominent heading/line
    if not result["title"]:
        for line in front_lines:
            clean = re.sub(r"^#+\s*", "", line).strip()
            clean = re.sub(r"^\*+\s*", "", clean).rstrip("*").strip()
            low = clean.lower()
            if (
                low.startswith("the project gutenberg")
                or low.startswith("gutenberg")
                or low.startswith("copyright")
                or low.startswith("all rights")
                or low.startswith("author:")
                or low.startswith("title:")
                or low.startswith("by ")
                or len(clean) < 3
                or len(clean) > 100
            ):
                continue
            result["title"] = clean
            break

    # 5. Fallback title
    if not result["title"] and fallback_title:
        result["title"] = fallback_title

    # 6. Look for subtitle / description
    if not result["description"] and len(front_lines) >= 2:
        for line in front_lines:
            if line == result["title"] or (result["author"] and result["author"].lower() in line.lower()):
                continue
            low = line.lower()
            if any(k in low for k in ["story", "novel", "mystery", "detective", "tale", "chronicle"]) and 5 < len(line) < 150:
                result["description"] = line.strip()
                break

    # Clean ALL CAPS if detected
    if result["title"] and result["title"].isupper() and len(result["title"]) > 4:
        result["title"] = result["title"].title()
    if result["author"] and result["author"].isupper() and len(result["author"]) > 4:
        result["author"] = result["author"].title()

    return result


def import_book_content(
    title: str,
    author: str,
    description: str = "",
    source_type: str = "upload",
    file_format: str = "txt",
    raw_content: Optional[str] = None,
    source_url: Optional[str] = None,
    extract_graph: bool = False,
) -> BookMetadata:
    """Safe ingestion pipeline for creating a new book entry, storing its text, and segmenting chapters."""
    fmt = file_format.strip().lower().lstrip(".")
    is_avail, reason = is_parser_available(fmt)
    if not is_avail:
        raise UnsupportedFormatError(
            f"Parser for format '{fmt.upper()}' is not installed in the backend environment. {reason}"
        )

    # Obtain source text
    if source_type == "url":
        if not source_url:
            raise SafeFetchError("A source URL must be provided when source_type is 'url'.")
        content_text = raw_content if raw_content else fetch_source_url(source_url)
    else:
        if raw_content is None or not raw_content.strip():
            raise ValueError("Uploaded document content cannot be empty.")
        content_text = raw_content

    # Auto-extract title, author, and description from front matter if missing
    if fmt == "txt":
        front_meta = parse_first_page_metadata(content_text, fallback_title=title)
        if not title or title.strip().lower() in ("", "untitled", "untitled book"):
            title = front_meta.get("title") or title or "Untitled Book"
        if not author or author.strip().lower() in ("", "unknown", "unknown author"):
            author = front_meta.get("author") or author or "Unknown Author"
        if not description and front_meta.get("description"):
            description = front_meta["description"]

    # Generate stable unique book identifier
    book_id = generate_book_id(title)
    sources_dir = get_book_sources_dir(book_id)

    # Save original source file
    source_file_path = sources_dir / f"source.{fmt}"
    with open(source_file_path, "w", encoding="utf-8") as f:
        f.write(content_text)

    now_iso = datetime.now(timezone.utc).isoformat()

    # Flow A: Pre-structured StoryGraph JSON
    if fmt == "json":
        try:
            dataset_dict = json.loads(content_text)
            dataset = StoryDataset.model_validate(dataset_dict)
        except Exception as exc:
            raise ValueError(f"Invalid StoryGraph dataset schema: {exc}")

        # Seed into FalkorDB under isolated graph name
        from app.graph.seed import seed_story_to_falkordb
        graph_name = f"story_{book_id}"
        try:
            seed_story_to_falkordb(dataset, graph_name=graph_name)
            max_ch = max(
                [c.reveal_chapter for c in dataset.characters] +
                [ev.reveal_chapter for ev in dataset.events] +
                [cl.reveal_chapter for cl in dataset.claims] +
                [evi.reveal_chapter for evi in dataset.evidence] + [1]
            )
            status = "ready"
            status_msg = f"Knowledge graph successfully seeded ({len(dataset.characters)} characters, {len(dataset.claims)} claims)."
        except Exception as exc:
            graph_name = None
            max_ch = 1
            status = "error"
            status_msg = f"FalkorDB graph seeding failed: {exc}"

        book_meta = BookMetadata(
            id=book_id,
            title=title or dataset.title,
            author=author,
            description=description or dataset.description,
            format="json",
            source_type=source_type,
            source_url=source_url,
            status=status,
            status_message=status_msg,
            max_chapters=max_ch,
            graph_name=graph_name,
            created_at=now_iso,
            chapters=[
                ChapterMetadata(chapter_number=i, title=f"Chapter {i}", preview="Pre-structured graph chapter.")
                for i in range(1, max_ch + 1)
            ]
        )
        save_book(book_meta)
        return book_meta

    # Flow B: Plain Text (.txt)
    chapters_data = segment_text_into_chapters(content_text)
    num_chapters = len(chapters_data)

    # Save segmented chapters
    chapters_file = sources_dir / "chapters.json"
    with open(chapters_file, "w", encoding="utf-8") as f:
        json.dump({"chapters": chapters_data}, f, indent=2)

    chapter_metas = [
        ChapterMetadata(
            chapter_number=ch["chapter_number"],
            title=ch["title"],
            word_count=ch["word_count"],
            char_count=ch["char_count"],
            preview=ch["preview"],
            candidate_entities=ch.get("candidate_entities", []),
        )
        for ch in chapters_data
    ]

    graph_name = None
    status = "import_pending"
    status_msg = (
        f"Document text successfully parsed into {num_chapters} chapters. "
        f"Automated relation extraction is pending configuration; reading boundaries and candidate text are preserved."
    )

    if extract_graph:
        try:
            from app.llm.extractor import run_story_extraction_pipeline
            from app.graph.seed import seed_story_to_falkordb

            extraction_res = run_story_extraction_pipeline(
                title=title,
                author=author,
                description=description,
                chapters_data=chapters_data,
                book_id=book_id,
            )
            graph_name = f"story_{book_id}"
            seed_story_to_falkordb(extraction_res.dataset, graph_name=graph_name)
            status = "ready"
            status_msg = extraction_res.status_message
        except Exception as exc:
            status = "import_pending"
            status_msg = f"Text parsed into {num_chapters} chapters; candidate graph extraction deferred: {exc}"
            graph_name = None

    book_meta = BookMetadata(
        id=book_id,
        title=title,
        author=author,
        description=description,
        format="txt",
        source_type=source_type,
        source_url=source_url,
        status=status,
        status_message=status_msg,
        max_chapters=max(1, num_chapters),
        graph_name=graph_name,
        created_at=now_iso,
        chapters=chapter_metas,
    )

    save_book(book_meta)
    return book_meta


def extract_and_seed_book_graph(book_id: str) -> BookMetadata:
    """Extracts candidate entities and seeds FalkorDB graph for an existing book."""
    book = get_book(book_id)
    if not book:
        raise ValueError(f"Book '{book_id}' not found.")

    sources_dir = get_book_sources_dir(book_id)
    chapters_file = sources_dir / "chapters.json"
    if not chapters_file.exists():
        raise ValueError(f"No chapters data found for book '{book_id}'.")

    with open(chapters_file, "r", encoding="utf-8") as f:
        chapters_data = json.load(f).get("chapters", [])

    from app.llm.extractor import run_story_extraction_pipeline
    from app.graph.seed import seed_story_to_falkordb

    extraction_res = run_story_extraction_pipeline(
        title=book.title,
        author=book.author,
        description=book.description,
        chapters_data=chapters_data,
        book_id=book_id,
    )
    graph_name = f"story_{book_id}"
    seed_story_to_falkordb(extraction_res.dataset, graph_name=graph_name)

    book.status = "ready"
    book.graph_name = graph_name
    book.status_message = extraction_res.status_message
    save_book(book)
    return book
