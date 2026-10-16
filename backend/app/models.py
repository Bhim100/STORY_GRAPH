"""Pydantic data models for StoryGraph."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class EntityNode(BaseModel):
    id: str
    name: str
    type: str  # Character, Clue, Location, Event, Secret
    description: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)


class RelationshipEdge(BaseModel):
    source: str
    target: str
    type: str  # KNOWS, LOCATED_AT, SUSPECTS, OWNS, PRESENT_AT, etc.
    properties: Dict[str, Any] = Field(default_factory=dict)


class StoryMetadata(BaseModel):
    id: str
    title: str
    summary: str
    victim: Optional[str] = None
    culprit: Optional[str] = None
    initial_unlocked_nodes: List[str] = Field(default_factory=list)
