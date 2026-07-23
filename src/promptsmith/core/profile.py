"""Typed profile contract shared by refinement backends."""

from typing import List, NotRequired, TypedDict


class RefinementProfile(TypedDict, total=False):
    """Configuration used to guide prompt refinement.

    Fields remain optional to preserve compatibility with existing YAML profiles,
    while giving backend implementations one explicit shared contract.
    """

    role: str
    domain: List[str]
    tone: str
    format: str
    constraints: List[str]
    description: NotRequired[str]
