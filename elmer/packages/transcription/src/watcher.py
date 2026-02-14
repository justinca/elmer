"""File watcher — monitors a directory for new audio files and queues transcription.

Runs as a standalone asyncio service. Uses watchdog for filesystem events
and processes files through the TranscriptionPipeline.
"""

import asyncio
import logging
import shutil
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer

from .config import settings
from .pipeline import TranscriptionPipeline

logger = logging.getLogger("elmer.transcription.watcher")

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}
# Wait after detecting a new file to ensure the write is complete.
SETTLE_DELAY = 2.0


class _AudioFileHandler(FileSystemEventHandler):
    """Watchdog handler that queues new audio files for transcription."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._queue = queue
        self._loop = loop

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            logger.info("Detected new audio file: %s", path.name)
            self._loop.call_soon_threadsafe(self._queue.put_nowait, str(path))


class FileWatcher:
    """Watches a directory for new audio files and transcribes them.

    Usage::

        watcher = FileWatcher()
        await watcher.run()  # blocks until stopped
    """

    def __init__(
        self,
        watch_dir: str | None = None,
        processed_dir: str | None = None,
    ):
        self.watch_dir = Path(watch_dir or settings.TRANSCRIPTION_WATCH_DIR)
        self.processed_dir = Path(processed_dir or settings.TRANSCRIPTION_PROCESSED_DIR)
        self._pipeline = TranscriptionPipeline()
        self._stop = asyncio.Event()

    async def run(self) -> None:
        """Start watching and processing. Blocks until stop() is called."""
        # Ensure directories exist.
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        await self._pipeline.connect_db()

        queue: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Process any files already in the inbox.
        for path in sorted(self.watch_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                logger.info("Found existing file in inbox: %s", path.name)
                queue.put_nowait(str(path))

        # Start watchdog observer (runs in its own thread).
        handler = _AudioFileHandler(queue, loop)
        observer = Observer()
        observer.schedule(handler, str(self.watch_dir), recursive=False)
        observer.start()
        logger.info("Watching %s for audio files...", self.watch_dir)

        try:
            while not self._stop.is_set():
                # Wait for a file or check stop every 2 seconds.
                try:
                    file_path = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue

                await self._process_file(file_path)
        finally:
            observer.stop()
            observer.join(timeout=5.0)
            await self._pipeline.close_db()
            logger.info("File watcher stopped.")

    def stop(self) -> None:
        """Signal the watcher to stop."""
        self._stop.set()

    async def _process_file(self, file_path: str) -> None:
        """Wait for the file to settle, transcribe, and move to processed."""
        path = Path(file_path)

        # Wait for the file write to complete.
        await asyncio.sleep(SETTLE_DELAY)

        if not path.is_file():
            logger.warning("File disappeared before processing: %s", path.name)
            return

        # Verify file size is stable (not still being written).
        size_1 = path.stat().st_size
        await asyncio.sleep(0.5)
        if path.is_file() and path.stat().st_size != size_1:
            logger.info("File still being written, waiting: %s", path.name)
            await asyncio.sleep(SETTLE_DELAY)

        try:
            logger.info("Processing %s...", path.name)
            result = await self._pipeline.transcribe_file(
                str(path),
                metadata={"source": "file_watcher", "watch_dir": str(self.watch_dir)},
            )
            logger.info(
                "Transcription complete: id=%d, %s, %.1fs duration, %d segments",
                result.id or 0,
                result.audio_file,
                result.duration_seconds or 0,
                len(result.segments),
            )

            # Move to processed directory.
            dest = self.processed_dir / path.name
            if dest.exists():
                # Avoid collision — append timestamp.
                dest = self.processed_dir / f"{path.stem}_{int(time.time())}{path.suffix}"
            shutil.move(str(path), str(dest))
            logger.info("Moved %s → %s", path.name, dest)

        except FileNotFoundError:
            logger.error("Audio file not found: %s", path)
        except RuntimeError as exc:
            logger.error("Transcription failed for %s: %s", path.name, exc)
        except Exception:
            logger.exception("Unexpected error processing %s", path.name)


async def main() -> None:
    """Entry point for running the watcher as a standalone service."""
    from elmer_common.logging import setup_logger as _setup_logger
    _setup_logger("elmer", logging.INFO)
    logger.info("Elmer Transcription Watcher starting...")
    watcher = FileWatcher()
    try:
        await watcher.run()
    except KeyboardInterrupt:
        watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
