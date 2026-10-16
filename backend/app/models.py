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
