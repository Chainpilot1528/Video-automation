"""Optional LLM-assisted research: suggestions only, never verdicts.

Suggestions are written to ``research/notes/`` as an import file, separate
from the ledger and from approved narration. Every suggested claim is forced
to ``unverified`` with no reviewer and no sources: a person has to find and
check the sources, then import and review the claim.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..providers.llm.base import LLMProvider
from ..schemas.research import Claim, ClaimOrigin, ClaimStatus, ClaimType, Importance
from ..utils.fs import write_json_atomic

SYSTEM_PROMPT = (
    "You help a documentary researcher list factual claims a script might make. "
    "Do not state whether claims are true, do not invent sources, citations or quotes. "
    'Reply with only a JSON array of objects: {"text": str, "claim_type": one of '
    f"{[t.value for t in ClaimType]}, \"importance\": one of {[i.value for i in Importance]}}}."
)
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


class SuggestionError(ValueError):
    """The provider's reply could not be turned into claim suggestions."""


def suggest_claims(provider: LLMProvider, brief: str, *, id_prefix: str = "sugg") -> list[Claim]:
    reply = provider.complete(f"Research brief:\n\n{brief}\n\nList the claims.", system=SYSTEM_PROMPT)
    match = _JSON_ARRAY_RE.search(reply)
    if not match:
        raise SuggestionError("provider reply contained no JSON array")
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise SuggestionError(f"provider reply was not valid JSON: {exc.msg}") from exc

    claims = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            continue
        claims.append(Claim(
            claim_id=f"{id_prefix}-{i:03d}",
            text=str(item["text"]).strip(),
            claim_type=_enum(ClaimType, item.get("claim_type"), ClaimType.FACTUAL),
            importance=_enum(Importance, item.get("importance"), Importance.SUPPORTING),
            # Whatever the model said, a suggestion starts unreviewed and unsourced.
            verification_status=ClaimStatus.UNVERIFIED,
            source_ids=[],
            origin=ClaimOrigin.LLM_SUGGESTION,
            caveats=[f"AI suggestion from provider '{provider.name}'; not researched or reviewed."],
        ))
    return claims


def write_suggestions(notes_dir: Path, claims: list[Claim], provider_name: str) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = notes_dir / f"suggestions-{stamp}.json"
    write_json_atomic(path, {
        "schema_version": "1.0",
        "note": f"AI suggestions from '{provider_name}'. Research sources before importing.",
        "claims": [c.model_dump(mode="json") for c in claims],
    })
    return path


def _enum(enum_cls, value, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default
