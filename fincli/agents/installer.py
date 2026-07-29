"""Write generated agent files into a project, merging shared files safely.

Fin-owned files are (re)written whole. Shared files (``AGENTS.md``,
``.github/copilot-instructions.md``) are only ever touched inside a marker
block, so hand-written content around it survives every re-run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from fincli.agents.targets import GENERATED_NOTE, GeneratedFile

BEGIN_MARK = "<!-- fin:agents:begin -->"
END_MARK = "<!-- fin:agents:end -->"


def _render_block(body: str) -> str:
    return f"{BEGIN_MARK}\n<!-- {GENERATED_NOTE} -->\n\n{body.rstrip()}\n{END_MARK}\n"


def merge_managed(existing: str | None, body: str) -> str:
    """Return *existing* with the fin marker block replaced by *body*.

    Creates the file content from scratch when *existing* is empty, replaces
    the current block when both markers are present, and appends a new block
    otherwise (including the pathological one-marker case — appending is safer
    than guessing where a half-deleted block ended).
    """
    block = _render_block(body)
    if existing is None or not existing.strip():
        return block
    start = existing.find(BEGIN_MARK)
    end = existing.find(END_MARK, start + 1 if start != -1 else 0)
    if start != -1 and end != -1:
        end += len(END_MARK)
        if end < len(existing) and existing[end] == "\n":
            end += 1
        return existing[:start] + block + existing[end:]
    return existing.rstrip() + "\n\n" + block


def install_files(
    root: Path, files: Iterable[GeneratedFile]
) -> list[tuple[GeneratedFile, str]]:
    """Write *files* under *root*; return (file, action) pairs.

    Actions: ``created`` (file did not exist), ``updated`` (content changed),
    ``unchanged`` (already up to date — nothing written), ``skipped``
    (``create_only`` file already exists — left untouched).
    """
    results: list[tuple[GeneratedFile, str]] = []
    for gf in files:
        target = root / gf.path
        existing = (
            target.read_text(encoding="utf-8", errors="replace")
            if target.exists()
            else None
        )
        if gf.create_only and existing is not None:
            results.append((gf, "skipped"))
            continue
        new = merge_managed(existing, gf.content) if gf.managed_block else gf.content
        if existing == new:
            results.append((gf, "unchanged"))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8")
        results.append((gf, "created" if existing is None else "updated"))
    return results
