"""Base model every qdt schema object inherits. Carries schema_version (ADR 0001, plan §4.3)."""

from pydantic import BaseModel, ConfigDict, Field


class QdtModel(BaseModel):
    """Common base: frozen, extra fields rejected, per-object schema_version."""

    # serialization-mode JSON Schema marks defaulted fields required: producers always emit them
    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )
    schema_version: int = Field(
        default=1,
        description=(
            "Per-object-type schema version; bumps only on breaking changes. "
            "Readers upgrade on load via migrations.py."
        ),
    )
