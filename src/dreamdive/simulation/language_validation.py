from __future__ import annotations


def require_language_guidance(language_guidance: str, *, context: str) -> str:
    cleaned = str(language_guidance or "").strip()
    if cleaned:
        return cleaned
    raise ValueError(
        "Language guidance is missing for {}. Re-run `ingest` so the meta layer includes "
        "`language_context`, then re-run `init` to refresh the session before "
        "continuing.".format(context)
    )
