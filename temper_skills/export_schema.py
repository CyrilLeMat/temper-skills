"""Render an inferred schema as editable Pydantic source — the inverse of
``ingest._to_json_schema``.

The schema is the *contract* the deterministic tree branches on (§4.1). Inference
drafts it; a human must ratify it. Persisting it as source (rather than accepting it
with a transient y/n) is what turns the contract into a reviewable, version-controlled
artifact — the same draft → ratify → freeze lifecycle proposed examples already have.
"""

from __future__ import annotations

from .ingest import InferredSchema

_PY_TYPE = {"string": "str", "number": "float", "integer": "int", "boolean": "bool"}


def _classname(fn_name: str) -> str:
    """route_ticket -> RouteTicket. A starting point the human can rename."""
    return "".join(part.capitalize() for part in fn_name.split("_")) or "Features"


def _looks_enum_like(description: str) -> bool:
    """A description that lists alternatives ("standard, low_fat, raw" / 'e.g. "a", "b"')
    is a closed set hiding in a free-text type — a candidate for Literal[...]."""
    d = description.lower()
    return description.count('"') >= 4 or description.count(",") >= 2 or "one of" in d


def normalization_notes(inferred: InferredSchema) -> dict[str, str]:
    """Per-field cautions surfaced at ratification time.

    Exact-match string features are only as safe as the normalizer feeding them, and an
    inferred ``str`` silently reopens a feature space that a ``Literal`` would close —
    the thrash failure mode. Naming both at ratification keeps the fuzziness in sight.
    """
    notes: dict[str, str] = {}
    for f in inferred.features:
        if f.type != "string":
            continue
        if _looks_enum_like(f.description):
            notes[f.name] = "looks enum-like — consider Literal[...] to close the space"
        else:
            notes[f.name] = "exact-match — your normalizer must emit canonical tokens"
    return notes


def render_schema_source(inferred: InferredSchema) -> str:
    cls = _classname(inferred.fn_name)
    lines = [
        "from __future__ import annotations",
        "",
        "from pydantic import BaseModel",
        "",
        "",
        f"# Proposed by temper-skills from the skill — THIS IS THE CONTRACT the deterministic",
        f"# tree branches on. Review every field (and the {cls} name) before pinning it with",
        f"#   temper-skills ingest <skill.md> --schema {{this_file}}:{cls}",
        f"class {cls}(BaseModel):",
    ]
    if not inferred.features:
        lines.append("    pass")
    for f in inferred.features:
        note = f"  # {f.description}" if f.description else ""
        lines.append(f"    {f.name}: {_PY_TYPE.get(f.type, 'str')}{note}")
    if inferred.constraints:
        lines.append("")
        lines.append("# Inferred hard constraints (pass these back via --constraint or Sources):")
        for c in inferred.constraints:
            lines.append(f"#   - {c}")
    return "\n".join(lines) + "\n"
