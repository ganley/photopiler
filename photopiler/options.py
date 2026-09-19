"""User-facing rendering options."""

import math
from dataclasses import dataclass
from enum import Enum

# Canvas area as a fraction of the summed photo areas (borders included).
# Below 1.0 the photos must overlap. The user can choose within MIN..MAX.
SCALE_FRACTION = 0.5
MIN_SCALE = 0.2
MAX_SCALE = 1.0


# Camera tilt away from straight overhead, in degrees. With the camera's lens
# (camera.FOCAL_LENGTH) the horizon would enter the frame at about 79°.
MAX_TILT = 65


def clamp_scale(value) -> float:
    """Keep a user-supplied scale within bounds; anything unusable becomes the default."""
    if value is None or not math.isfinite(value):
        return SCALE_FRACTION
    return max(MIN_SCALE, min(MAX_SCALE, value))


def clamp_tilt(value) -> float:
    """Keep a user-supplied tilt within bounds; anything unusable means overhead."""
    if value is None or not math.isfinite(value):
        return 0.0
    return max(0.0, min(MAX_TILT, value))


class Border(str, Enum):
    NONE = "none"
    INSTAMATIC = "instamatic"
    POLAROID = "polaroid"
    RANDOM = "random"


class Tone(str, Enum):
    COLOR = "color"
    MONO = "mono"
    RANDOM = "random"


class Age(str, Enum):
    NONE = "none"
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    RANDOM = "random"


@dataclass(frozen=True)
class PileOptions:
    seed: int
    scale: float = SCALE_FRACTION
    border: Border = Border.RANDOM
    tone: Tone = Tone.COLOR
    age: Age = Age.NONE
    tilt: float = 0.0  # camera angle away from overhead, in degrees


def parse_enum(enum_cls, value, default):
    """Look up an enum member by value, falling back to `default` if missing or invalid."""
    try:
        return enum_cls(value)
    except ValueError:
        return default
