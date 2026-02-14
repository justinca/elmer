"""Folder watcher — polls a directory for audio files and transcribes them.

Runs in a dedicated daemon thread. After transcription, posts the JSON
result to Core's /transcription/ingest endpoint and moves the source
file to a 'processed' subfolder.
"""

import logging
import shutil
import threading
import time
from pathlib import Path

import httpx

from ..config import settings
from .whisper_service import transcribe, SUPPORTED_EXTENSIONS

logger = logging.getLogger("elmer.worker.folder_watcher")

CORE_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

# Files modified less than this many seconds ago are skipped (OneDrive sync guard).
SYNC_SETTLE_SECONDS = 60


def _post_to_core(filename: str, result: dict) -> dict | None:
    """POST transcription result JSON to Core's ingest endpoint."""
    url = f"{settings.core_base_url}/transcription/ingest"
    payload = {
        "audio_file": filename,
        "transcript": result.get("text", ""),
        "segments": result.get("segments", []),
        "language": result.get("language"),
        "duration_seconds": result.get("duration"),
        "model": result.get("model"),
        "diarized": result.get("diarized", False),
        "speakers": result.get("speakers", []),
        "source": "folder_watcher",
    }
    try:
        with httpx.Client(timeout=CORE_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Ingested to Core: id=%s", data.get("id"))
            return data
    except Exception as exc:
        logger.error("Failed to post to Core: %s", exc)
        return None


def _process_file(file_path: Path, processed_dir: Path) -> None:
    """Transcribe a single audio file and move it to processed."""
    filename = file_path.name
    size_mb = file_path.stat().st_size / (1024 * 1024)

    logger.info("Processing %s (%.1f MB)", filename, size_mb)
    start = time.time()

    # Transcribe locally with diarization.
    result = transcribe(file_path, diarize=True)

    elapsed = time.time() - start
    logger.info(
        "Transcribed %s in %.1fs (%.1fs audio)",
        filename, elapsed, result.get("duration", 0),
    )

    # Send result to Core for DB storage + embedding.
    _post_to_core(filename, result)

    # Move to processed folder.
    dest = processed_dir / filename
    if dest.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dest = processed_dir / f"{stem}_{timestamp}{suffix}"

    shutil.move(str(file_path), str(dest))
    logger.info("Moved %s → processed/%s", filename, dest.name)


def _watcher_thread(stop_event: threading.Event) -> None:
    """Poll the watch folder for new audio files."""
    watch_dir = Path(settings.WATCH_FOLDER)
    processed_dir = watch_dir / "processed"

    if not watch_dir.is_dir():
        logger.error("Watch folder does not exist: %s", watch_dir)
        return

    processed_dir.mkdir(exist_ok=True)

    logger.info(
        "Folder watcher active: %s (every %ds, extensions: %s)",
        watch_dir,
        settings.WATCH_INTERVAL_SECONDS,
        ", ".join(SUPPORTED_EXTENSIONS),
    )

    while not stop_event.is_set():
        try:
            # List top-level audio files, sorted oldest first.
            now = time.time()
            candidates = []
            for f in watch_dir.iterdir():
                if not f.is_file():
                    continue
                if f.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                # Skip files still being synced.
                if now - f.stat().st_mtime < SYNC_SETTLE_SECONDS:
                    logger.debug("Skipping %s (recently modified)", f.name)
                    continue
                # Skip if already processed.
                if (processed_dir / f.name).exists():
                    continue
                candidates.append(f)

            candidates.sort(key=lambda p: p.stat().st_mtime)

            if candidates:
                logger.info("Found %d new audio file(s) to process", len(candidates))

            for file_path in candidates:
                if stop_event.is_set():
                    break
                try:
                    _process_file(file_path, processed_dir)
                except PermissionError:
                    logger.warning("Skipping %s (file locked)", file_path.name)
                except Exception:
                    logger.exception("Error processing %s", file_path.name)

        except Exception:
            logger.exception("Folder watcher cycle error")

        stop_event.wait(timeout=settings.WATCH_INTERVAL_SECONDS)


def start_watcher() -> tuple[threading.Event, threading.Thread]:
    """Start the folder watcher in a daemon thread."""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_watcher_thread,
        args=(stop_event,),
        daemon=True,
        name="folder-watcher",
    )
    thread.start()
    return stop_event, thread
