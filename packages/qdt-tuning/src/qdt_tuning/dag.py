"""The order a tune-up runs its nodes in (ADR 0050): a topological sort over `depends_on`."""

from collections.abc import Iterable

from qdt_schemas.modeling import CalibrationNode


def order(nodes: Iterable[CalibrationNode]) -> tuple[CalibrationNode, ...]:
    """`nodes` sorted so that every dependency comes before its dependents, keeping the given order
    among nodes that are otherwise free (Kahn's algorithm, stable). Raises ValueError for a repeated
    node id, a dependency that is not in `nodes`, or a cycle."""
    given = list(nodes)
    ids = [n.node_id for n in given]
    if len(set(ids)) != len(ids):
        raise ValueError("node ids must be unique")
    by_id = {n.node_id: n for n in given}
    for n in given:
        # a dependency may be absent when every input taken from it has a held-level fallback: the
        # node then runs on its own, centred on the stand's operating point (a retune, ADR 0062)
        missing = set()
        for d in set(n.depends_on) - set(by_id):
            taken = [b for b in n.inputs if b.node_id == d]
            if not (taken and all(b.held for b in taken)):
                missing.add(d)
        if missing:
            raise ValueError(
                f"node {n.node_id!r} depends on {sorted(missing)}, which are not in the tune-up"
            )
    placed: list[CalibrationNode] = []
    done: set[str] = set()
    remaining = list(given)
    while remaining:
        ready = [n for n in remaining if set(n.depends_on) & set(by_id) <= done]
        if not ready:
            raise ValueError(
                f"nodes {[n.node_id for n in remaining]} depend on each other in a cycle"
            )
        for n in ready:
            placed.append(n)
            done.add(n.node_id)
        remaining = [n for n in remaining if n.node_id not in done]
    return tuple(placed)
