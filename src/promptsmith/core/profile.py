"""Typed profile contract shared by refinement backends."""

from typing import TypedDict


class RefinementProfile(TypedDict, total=False):
    """Configuration used to guide prompt refinement.

    Fields remain optional to preserve compatibility with existing YAML profiles,
    while giving backend implementations one explicit shared contract.
    """

    role: str
    domain: list[str]
    tone: str
    format: str
    constraints: list[str]
    description: str
    backend: str
