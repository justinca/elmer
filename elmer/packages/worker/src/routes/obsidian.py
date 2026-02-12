"""Obsidian vault access — list, read, and query markdown notes."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Query

from ..config import settings

router = APIRouter()
logger = logging.getLogger("elmer.worker.obsidian")

# Directories to skip when scanning the vault.
_SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules"}

# Binary/media extensions to ignore.
_SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico", ".webp",
    ".pdf", ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".webm",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib",
}


# --- Helpers ---


def _get_vault_path() -> Path:
    """Return the configured vault path, raising 503 if not available."""
    if not settings.OBSIDIAN_VAULT_PATH:
        raise HTTPException(
            status_code=503,
            detail="OBSIDIAN_VAULT_PATH not configured on the worker",
        )
    vault = Path(settings.OBSIDIAN_VAULT_PATH)
    if not vault.is_dir():
        raise HTTPException(
            status_code=503,
            detail=f"Vault directory not found: {vault}",
        )
    return vault


def _should_skip(path: Path, vault: Path) -> bool:
    """Check if a file should be skipped during vault scanning."""
    relative = path.relative_to(vault)
    # Skip if any parent directory is in the skip list.
    for part in relative.parts[:-1]:
        if part in _SKIP_DIRS:
            return True
    # Skip non-markdown and binary files.
    if path.suffix.lower() != ".md":
        return True
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return True
    return False


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown content.

    Returns (frontmatter_dict, body_without_frontmatter).
    """
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    yaml_block = content[3:end].strip()
    body = content[end + 3:].strip()
    try:
        fm = yaml.safe_load(yaml_block) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _extract_tags(content: str, frontmatter: dict) -> list[str]:
    """Extract tags from both frontmatter and inline #tags."""
    tags: set[str] = set()

    # Frontmatter tags (list or comma-separated string).
    fm_tags = frontmatter.get("tags", [])
    if isinstance(fm_tags, str):
        fm_tags = [t.strip() for t in fm_tags.split(",")]
    if isinstance(fm_tags, list):
        tags.update(str(t).strip().lstrip("#") for t in fm_tags if t)

    # Inline #tags — match #word but not inside [[links]] or `code`.
    for match in re.finditer(r"(?<!\[)(?<!`)#([a-zA-Z][\w/-]*)", content):
        tags.add(match.group(1))

    return sorted(tags)


def _extract_wikilinks(content: str) -> list[str]:
    """Extract [[wikilink]] targets from content."""
    links = []
    for match in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content):
        links.append(match.group(1).strip())
    return sorted(set(links))


def _note_summary(md_file: Path, vault: Path) -> dict | None:
    """Build a summary dict for a single markdown file."""
    try:
        stat = md_file.stat()
        content = md_file.read_text(encoding="utf-8", errors="replace")
        fm, _ = _parse_frontmatter(content)
        tags = _extract_tags(content, fm)
        title = fm.get("title") or md_file.stem
        return {
            "path": str(md_file.relative_to(vault)),
            "title": title,
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            "size_bytes": stat.st_size,
            "tags": tags,
        }
    except Exception as exc:
        logger.warning("Failed to read %s: %s", md_file, exc)
        return None


# --- Endpoints ---


@router.get("/notes")
async def list_notes():
    """List all markdown files in the Obsidian vault."""
    vault = _get_vault_path()
    notes = []
    for md_file in vault.rglob("*.md"):
        if _should_skip(md_file, vault):
            continue
        summary = _note_summary(md_file, vault)
        if summary is not None:
            notes.append(summary)
    return notes


@router.get("/note")
async def get_note(path: str = Query(..., description="Relative path within vault")):
    """Read a specific note by its relative path."""
    vault = _get_vault_path()
    full_path = (vault / path).resolve()

    # Prevent path traversal outside the vault.
    try:
        full_path.relative_to(vault.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    if not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")

    content = full_path.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_frontmatter(content)
    tags = _extract_tags(content, fm)
    links = _extract_wikilinks(body)
    stat = full_path.stat()
    title = fm.get("title") or full_path.stem

    return {
        "path": path,
        "title": title,
        "content": content,
        "frontmatter": fm,
        "tags": tags,
        "links": links,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }


@router.get("/notes/changed")
async def list_changed_notes(
    since: str = Query(..., description="ISO8601 timestamp"),
):
    """List notes modified since a given timestamp."""
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ISO8601 timestamp")

    vault = _get_vault_path()
    changed = []
    for md_file in vault.rglob("*.md"):
        if _should_skip(md_file, vault):
            continue
        try:
            stat = md_file.stat()
            mod_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if mod_dt > since_dt:
                summary = _note_summary(md_file, vault)
                if summary is not None:
                    changed.append(summary)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", md_file, exc)
    return changed
