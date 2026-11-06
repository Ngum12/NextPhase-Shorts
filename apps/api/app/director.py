"""Safe, deterministic director contract for staged AI integration.

No third-party AI calls by default. Codex Phase 3 implements provider adapters,
transcription and semantic shot planning in this interface.
"""
from dataclasses import dataclass
from enum import Enum

class SceneType(str, Enum):
    TALKING_HEAD = "talking_head"
    B_ROLL = "b_roll"
    EDITORIAL_CARD = "editorial_card"
    MOTION_2D = "motion_2d"
    PRODUCT_3D = "product_3d"

@dataclass(frozen=True)
class Scene:
    kind: SceneType
    start_seconds: float
    end_seconds: float
    source_start_seconds: float | None = None
    asset_id: str | None = None
    caption: str | None = None

@dataclass(frozen=True)
class EditDecisionList:
    style: str
    output_seconds: float
    scenes: tuple[Scene, ...]

    def validate(self) -> None:
        if not 5 <= self.output_seconds <= 60:
            raise ValueError("Output duration must be 5–60 seconds")
        if not self.scenes:
            raise ValueError("An edit requires at least one scene")
        cursor = 0.0
        for scene in self.scenes:
            if abs(scene.start_seconds - cursor) > 0.001 or scene.end_seconds <= scene.start_seconds:
                raise ValueError("Scene timeline must be contiguous, ordered, and positive")
            if scene.end_seconds > 60.001:
                raise ValueError("Scene exceeds 60 seconds")
            cursor = scene.end_seconds
        if abs(cursor - self.output_seconds) > 0.001:
            raise ValueError("Scene timeline must equal output duration")

def fallback_edl(style: str, source_seconds: float, requested_seconds: int) -> EditDecisionList:
    out = min(float(requested_seconds), float(source_seconds), 60.0)
    edl = EditDecisionList(style=style, output_seconds=out, scenes=(Scene(SceneType.TALKING_HEAD, 0, out, 0),))
    edl.validate()
    return edl
