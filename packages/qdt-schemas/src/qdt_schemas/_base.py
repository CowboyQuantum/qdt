"""Base model every qdt schema object inherits. Carries schema_version (ADR 0001, plan §4.3)."""

import hashlib
import json

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

    def canonical_json(self) -> str:
        """JSON with sorted keys and no whitespace: equal objects give equal text (ADR 0025)."""
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        )

    def content_sha256(self) -> str:
        """Hex SHA-256 of `canonical_json()`: the content address the registry indexes by (ADR 0025)."""
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()
