"""
Bounding-box annotation resolution.

Converts bbox_annotations (PDF-point bounding boxes keyed by page) into
standard TOKEN_LABEL annotation dicts by matching against PAWLs tokens.
"""

from __future__ import annotations

import logging
from typing import Optional, Union

from typing_extensions import NotRequired, TypedDict

from opencontractserver.types.dicts import BoundingBoxPythonType

logger = logging.getLogger(__name__)


class BboxAnnotationType(TypedDict):
    """A bounding-box annotation entry in import data."""

    id: NotRequired[Optional[Union[str, int]]]
    annotationLabel: str
    rawText: str
    bounds: dict[str, list[BoundingBoxPythonType]]  # page (str) -> rects
    parent_id: NotRequired[Optional[Union[str, int]]]
    structural: NotRequired[bool]
    long_description: NotRequired[Optional[str]]
