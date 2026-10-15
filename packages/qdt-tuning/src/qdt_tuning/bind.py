"""Fill a node's definition from upstream outcomes (ADR 0049): `inputs` name the paths, `bind` sets them.

A path is dotted: field names and sequence indices into the node's `SweepDefinition` as it serializes
(`axes.0.couplings.P2`, `stage.sequence.body.0.level.scale`). The definition is dumped, the values are
set, and it is validated again, so a binding that breaks the sweep fails here, before anything runs.
"""

from collections.abc import Mapping
from typing import Any

from qdt_schemas.activity import SweepDefinition
from qdt_schemas.modeling import CalibrationNode, NodeOutcome


def set_path(data: Any, path: str, value: Any) -> None:
    """Set `value` at the dotted `path` inside nested dicts and lists, in place."""
    parts = path.split(".")
    node = data
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if isinstance(node, list):
            try:
                index = int(part)
            except ValueError:
                raise KeyError(f"{'.'.join(parts[: i + 1])}: {part!r} is not an index") from None
            if not 0 <= index < len(node):
                raise KeyError(f"{'.'.join(parts[: i + 1])}: index {index} out of range")
            if last:
                node[index] = value
            else:
                node = node[index]
        elif isinstance(node, dict):
            if last:
                node[part] = value  # a new key is allowed: a coupling for a channel not yet coupled
            else:
                if part not in node or node[part] is None:
                    raise KeyError(f"{'.'.join(parts[: i + 1])}: no such field")
                node = node[part]
        else:
            raise KeyError(f"{'.'.join(parts[:i])}: not a container")


def bind(node: CalibrationNode, outcomes: Mapping[str, NodeOutcome]) -> CalibrationNode:
    """The node with every `inputs` binding filled from `outcomes` (node id → accepted outcome).

    Raises KeyError for a missing upstream outcome or output name or an unknown path, ValueError for an
    upstream outcome that is not `accepted` or a bound definition that does not validate."""
    if not node.inputs:
        return node
    data = node.definition.model_dump(
        mode="json"
    )  # tuples become lists, which a path can index into
    for b in node.inputs:
        if b.node_id not in outcomes:
            raise KeyError(f"node {node.node_id!r} needs an outcome of {b.node_id!r}")
        upstream = outcomes[b.node_id]
        if upstream.status != "accepted":
            raise ValueError(
                f"node {node.node_id!r} needs {b.node_id!r} accepted; it is {upstream.status}"
            )
        if b.output not in upstream.outputs:
            raise KeyError(
                f"{b.node_id!r} has no output {b.output!r}; has {sorted(upstream.outputs)}"
            )
        set_path(data, b.target, upstream.outputs[b.output])
    try:
        definition = SweepDefinition.model_validate(data)
    except ValueError as e:
        raise ValueError(
            f"node {node.node_id!r}: the bound definition does not validate: {e}"
        ) from e
    return node.model_copy(update={"definition": definition})
