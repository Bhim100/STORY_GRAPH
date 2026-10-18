"""Pydantic data models for StoryGraph schema entities and mystery stories."""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class Character(BaseModel):
    id: str
    story_id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    role: str
    reveal_chapter: int


class Location(BaseModel):
    id: str
    story_id: str
    name: str
    reveal_chapter: int


class Faction(BaseModel):
    id: str
    story_id: str
    name: str
    reveal_chapter: int


class Event(BaseModel):
    id: str
    story_id: str
    title: str
    event_chapter: int
    reveal_chapter: int


class Claim(BaseModel):
    id: str
    story_id: str
    kind: str  # Relationship type (e.g. EMPLOYED_BY, KIN_OF, CAUSED, PARTICIPATED_IN, etc.)
    subject: str
    object: str
    role: Optional[str] = None  # e.g., perpetrator, victim, discoverer, beneficiary
    text: str
    reveal_chapter: int
    superseded_by: Optional[str] = None
    validation: str = "confirmed"  # confirmed, alleged, false_lead, debunked


class Evidence(BaseModel):
    id: str
    story_id: str
    kind: Literal["document", "testimony", "object"]
    excerpt: str
    source_chapter: int
    reveal_chapter: int
    supports: List[str] = Field(default_factory=list)  # List of claim IDs


class StoryDataset(BaseModel):
    story_id: str
    title: str
    description: str
    characters: List[Character] = Field(default_factory=list)
    locations: List[Location] = Field(default_factory=list)
    factions: List[Faction] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    claims: List[Claim] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)


class ChapterMetadata(BaseModel):
    chapter_number: int
    title: str
    word_count: int = 0
    char_count: int = 0
    preview: str = ""
    candidate_entities: List[str] = Field(default_factory=list)


class BookMetadata(BaseModel):
    id: str
    title: str
    author: str
    description: str = ""
    format: str = "txt"  # txt, json, epub, pdf
    source_type: str = "upload"  # upload, url, bundled
    source_url: Optional[str] = None
    status: str = "ready"  # ready, import_pending, parsing_completed, error, unsupported_format
    status_message: Optional[str] = None
    max_chapters: int = 1
    graph_name: Optional[str] = None
    created_at: Optional[str] = None
    chapters: List[ChapterMetadata] = Field(default_factory=list)


class AddBookRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default="", max_length=2000)
    source_type: Literal["upload", "url"] = "upload"
    format: str = "txt"
    source_url: Optional[str] = None
    content: Optional[str] = None
    extract_graph: Optional[bool] = False


class BookListResponse(BaseModel):
    books: List[BookMetadata]

