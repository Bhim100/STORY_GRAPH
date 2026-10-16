"""Spoiler and reveal-boundary rule enforcement."""
from typing import Set


class SpoilerGuard:
    """Manages player visibility boundaries and prevents premature reveals."""

    def __init__(self, unlocked_nodes: Set[str] = None):
        self.unlocked_nodes = unlocked_nodes or set()

    def is_visible(self, node_id: str) -> bool:
        return node_id in self.unlocked_nodes

    def unlock_node(self, node_id: str) -> None:
        self.unlocked_nodes.add(node_id)
