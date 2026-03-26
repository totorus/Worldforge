"""Pydantic schemas for narrator pipeline outputs — used for validation after JSON parsing."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ── Step 1: Era splitting ────────────────────────────────────────────────────

class Era(BaseModel):
    name: str = "Ère sans nom"
    start_year: int | float = 0
    end_year: int | float = 0
    description: str = ""
    key_events: list[str] = Field(default_factory=list)


# ── Step 2: Naming ───────────────────────────────────────────────────────────
# Output is dict[str, str] — no schema needed, validated inline.


# ── Step 3: Faction sheet ────────────────────────────────────────────────────

class FactionSheet(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    culture: str = ""
    governance_description: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    notable_moments: list[str] = Field(default_factory=list)
    current_state: str = ""

    class Config:
        extra = "allow"


# ── Step 4: Region sheet ────────────────────────────────────────────────────

class RegionSheet(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    landscape: str = ""
    resources_description: str = ""
    strategic_importance: str = ""
    notable_events: list[str] = Field(default_factory=list)
    atmosphere: str = ""

    class Config:
        extra = "allow"


# ── Step 5: Event narrative ──────────────────────────────────────────────────

class NarratedEvent(BaseModel):
    year: int | float | None = None
    event_id: str = ""
    era: str = ""
    title: str = ""
    narrative: str = ""
    involved_factions: list[str] = Field(default_factory=list)
    consequences_narrative: str = ""

    class Config:
        extra = "allow"


# ── Step 6: Character biography ─────────────────────────────────────────────

class CharacterBio(BaseModel):
    name: str = ""
    role: str = ""
    faction: str = ""
    birth_year: int | float | None = None
    death_year: int | float | None = None
    biography: str = ""
    personality: str = ""
    legacy: str = ""

    class Config:
        extra = "allow"


# ── Step 7: Legend ───────────────────────────────────────────────────────────

class Legend(BaseModel):
    title: str = ""
    era_origin: str = ""
    type: str = ""
    narrative: str = ""
    moral: str = ""
    related_factions: list[str] = Field(default_factory=list)
    related_characters: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"


# ── Step 9: Coherence report ────────────────────────────────────────────────

class CoherenceReport(BaseModel):
    score: float = 0.5
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v):
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return 0.5

    class Config:
        extra = "allow"


# ── Entity detection ────────────────────────────────────────────────────────

class DetectedEntity(BaseModel):
    name: str
    type: str
    context: str = ""

    class Config:
        extra = "allow"


# ── Mapping step name → (schema, is_list) for pipeline validation ────────

STEP_SCHEMAS: dict[str, tuple[type[BaseModel] | None, bool]] = {
    "eras": (Era, True),
    "names": (None, False),  # dict[str, str], validated inline
    "factions": (FactionSheet, True),
    "regions": (RegionSheet, True),
    "events": (NarratedEvent, True),
    "characters": (CharacterBio, True),
    "legends": (Legend, True),
    "coherence_report": (CoherenceReport, False),
}


def validate_step_output(step_key: str, data) -> tuple[any, list[str]]:
    """Validate and coerce pipeline step output using Pydantic schemas.

    Returns:
        (validated_data, errors) — errors is a list of warning strings.
        validated_data is the coerced output (with defaults filled in).
        If the schema doesn't match at all, returns (data, errors) unchanged.
    """
    schema_info = STEP_SCHEMAS.get(step_key)
    if not schema_info or schema_info[0] is None:
        return data, []

    schema_cls, is_list = schema_info
    errors = []

    if is_list:
        if not isinstance(data, list):
            errors.append(f"[{step_key}] Expected list, got {type(data).__name__}")
            return data, errors

        validated = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                errors.append(f"[{step_key}][{i}] Expected dict, got {type(item).__name__}")
                validated.append(item)
                continue
            try:
                obj = schema_cls.model_validate(item)
                validated.append(obj.model_dump(exclude_none=False))
            except Exception as e:
                errors.append(f"[{step_key}][{i}] Validation warning: {e}")
                validated.append(item)  # keep raw data on validation failure
        return validated, errors

    else:
        if not isinstance(data, dict):
            errors.append(f"[{step_key}] Expected dict, got {type(data).__name__}")
            return data, errors
        try:
            obj = schema_cls.model_validate(data)
            return obj.model_dump(exclude_none=False), errors
        except Exception as e:
            errors.append(f"[{step_key}] Validation warning: {e}")
            return data, errors
