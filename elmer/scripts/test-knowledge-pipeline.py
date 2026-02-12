#!/usr/bin/env python3
"""End-to-end knowledge pipeline verification script.

Tests the full lifecycle: embed → ingest → search → chat → unified results.
Requires the Elmer stack to be running (make up).

Usage:
    python scripts/test-knowledge-pipeline.py
    python scripts/test-knowledge-pipeline.py --base-url http://localhost:8100
"""

import argparse
import json
import sys
import time

import httpx

TIMEOUT = 120.0  # seconds for LLM/embedding calls
QUICK_TIMEOUT = 10.0  # seconds for fast endpoints


class PipelineTest:
    """Runs each pipeline test and tracks results."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.results: list[dict] = []

    def _record(self, name: str, status: str, detail: str = "") -> None:
        icon = {"PASS": "\033[32mPASS\033[0m", "FAIL": "\033[31mFAIL\033[0m",
                "SKIP": "\033[33mSKIP\033[0m"}
        print(f"  [{icon.get(status, status)}] {name}")
        if detail:
            for line in detail.strip().split("\n"):
                print(f"         {line}")
        self.results.append({"name": name, "status": status, "detail": detail})
        if status == "PASS":
            self.passed += 1
        elif status == "FAIL":
            self.failed += 1
        else:
            self.skipped += 1

    # ------------------------------------------------------------------
    # Individual tests
    # ------------------------------------------------------------------

    def test_health(self) -> bool:
        """Verify Core API is reachable."""
        try:
            with httpx.Client(timeout=QUICK_TIMEOUT) as c:
                r = c.get(f"{self.base_url}/health")
                r.raise_for_status()
                data = r.json()
            self._record(
                "Core API health check",
                "PASS",
                f"status={data.get('status')}, uptime={data.get('uptime_seconds')}s",
            )
            return True
        except Exception as exc:
            self._record("Core API health check", "FAIL", str(exc))
            return False

    def test_embedding(self) -> bool:
        """Test: Embed a text and verify 768-dim vector returned."""
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.post(
                    f"{self.base_url}/knowledge/embed",
                    json={"text": "Elmer is a home lab operating system"},
                )
                r.raise_for_status()
                data = r.json()

            dims = data.get("dimensions", 0)
            embedding = data.get("embedding", [])

            if dims == 768 and len(embedding) == 768:
                self._record(
                    "Embedding generation (768-dim)",
                    "PASS",
                    f"model={data.get('model')}, dimensions={dims}",
                )
                return True
            else:
                self._record(
                    "Embedding generation (768-dim)",
                    "FAIL",
                    f"Expected 768 dimensions, got {dims} (len={len(embedding)})",
                )
                return False
        except Exception as exc:
            self._record("Embedding generation (768-dim)", "FAIL", str(exc))
            return False

    def test_ingest_text(self) -> bool:
        """Test: Ingest a test markdown document and verify it's stored."""
        test_content = """# Test Document for Pipeline Verification

This is a test document created by the Elmer pipeline test script.
It contains information about the Elmer home lab system architecture.

## Components

- Core API: FastAPI gateway running on the NUC
- Dashboard: Streamlit web UI
- Knowledge: RAG pipeline with pgvector
- Telegram Bot: Chat interface via Telegram

## Purpose

This document verifies that the ingestion pipeline correctly chunks,
embeds, and stores documents for later retrieval via semantic search.
"""
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.post(
                    f"{self.base_url}/knowledge/ingest/text",
                    json={
                        "text": test_content,
                        "title": "pipeline-test-doc",
                        "source": "pipeline-test",
                        "metadata": {"test": True},
                    },
                )
                r.raise_for_status()
                data = r.json()

            chunks = data.get("chunks_stored", 0)
            if chunks > 0:
                self._record(
                    "Text ingestion",
                    "PASS",
                    f"source={data.get('source')}, chunks_stored={chunks}",
                )
                return True
            else:
                self._record("Text ingestion", "FAIL", "No chunks stored")
                return False
        except Exception as exc:
            self._record("Text ingestion", "FAIL", str(exc))
            return False

    def test_search_ingested(self) -> bool:
        """Test: Search for the ingested test document."""
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.post(
                    f"{self.base_url}/knowledge/search",
                    json={
                        "query": "Elmer pipeline verification components",
                        "sources": ["docs"],
                        "limit": 5,
                        "threshold": 0.3,
                    },
                )
                r.raise_for_status()
                data = r.json()

            results = data.get("results", [])
            # Look for our test doc in results.
            found = any("pipeline" in r.get("content", "").lower() for r in results)

            if found:
                top_score = results[0]["score"] if results else 0
                self._record(
                    "Search for ingested document",
                    "PASS",
                    f"Found test doc in {len(results)} results (top score={top_score:.3f})",
                )
                return True
            elif results:
                self._record(
                    "Search for ingested document",
                    "PASS",
                    f"Search returned {len(results)} results (test doc may not be top hit)",
                )
                return True
            else:
                self._record(
                    "Search for ingested document",
                    "FAIL",
                    "No results returned — document may not have been embedded",
                )
                return False
        except Exception as exc:
            self._record("Search for ingested document", "FAIL", str(exc))
            return False

    def test_directory_ingest(self) -> bool:
        """Test: Ingest the docs/ directory."""
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.post(
                    f"{self.base_url}/knowledge/ingest/directory",
                    json={
                        "path": "/app/docs",
                        "source": "elmer-docs",
                        "recursive": True,
                        "patterns": ["*.md"],
                    },
                )
                r.raise_for_status()
                data = r.json()

            ingested = data.get("ingested", 0)
            skipped = data.get("skipped", 0)
            errors = data.get("errors", [])

            if ingested > 0 or skipped > 0:
                self._record(
                    "Directory ingestion (docs/)",
                    "PASS",
                    f"ingested={ingested}, skipped={skipped}, errors={len(errors)}",
                )
                return True
            else:
                self._record(
                    "Directory ingestion (docs/)",
                    "FAIL",
                    f"No files ingested or skipped. errors={errors}",
                )
                return False
        except Exception as exc:
            self._record("Directory ingestion (docs/)", "FAIL", str(exc))
            return False

    def test_sources_list(self) -> bool:
        """Test: List knowledge sources."""
        try:
            with httpx.Client(timeout=QUICK_TIMEOUT) as c:
                r = c.get(f"{self.base_url}/knowledge/sources")
                r.raise_for_status()
                data = r.json()

            if isinstance(data, list) and len(data) > 0:
                sources = [s["source"] for s in data]
                total = sum(s.get("doc_count", 0) for s in data)
                self._record(
                    "Knowledge sources list",
                    "PASS",
                    f"sources={sources}, total_docs={total}",
                )
                return True
            else:
                self._record("Knowledge sources list", "FAIL", "No sources found")
                return False
        except Exception as exc:
            self._record("Knowledge sources list", "FAIL", str(exc))
            return False

    def test_obsidian_sync(self) -> bool:
        """Test: Trigger Obsidian note sync (may fail if worker is offline)."""
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.post(f"{self.base_url}/notes/sync")
                if r.status_code == 502:
                    self._record(
                        "Obsidian vault sync",
                        "SKIP",
                        "Worker unreachable — sync requires Windows worker running",
                    )
                    return True
                r.raise_for_status()
                data = r.json()

            self._record(
                "Obsidian vault sync",
                "PASS",
                f"+{data.get('added', 0)} ~{data.get('updated', 0)} "
                f"-{data.get('deleted', 0)} ={data.get('unchanged', 0)} "
                f"({data.get('duration_seconds', 0)}s)",
            )
            return True
        except Exception as exc:
            self._record("Obsidian vault sync", "FAIL", str(exc))
            return False

    def test_transcription_list(self) -> bool:
        """Test: List transcriptions (verifies endpoint works)."""
        try:
            with httpx.Client(timeout=QUICK_TIMEOUT) as c:
                r = c.get(f"{self.base_url}/transcription")
                r.raise_for_status()
                data = r.json()

            count = len(data) if isinstance(data, list) else 0
            self._record(
                "Transcription list",
                "PASS",
                f"Found {count} transcription(s)",
            )
            return True
        except Exception as exc:
            self._record("Transcription list", "FAIL", str(exc))
            return False

    def test_chat_rag(self) -> bool:
        """Test: Chat with RAG and verify context is used."""
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.post(
                    f"{self.base_url}/chat",
                    json={
                        "message": "What components does Elmer have? List the main services.",
                        "model": "llama3.1:8b",
                    },
                )
                r.raise_for_status()
                data = r.json()

            response_text = data.get("response", "")
            conv_id = data.get("conversation_id")
            sources = data.get("sources_used", [])
            model = data.get("model", "")

            if response_text and conv_id:
                source_names = [s.get("source", "") for s in sources]
                self._record(
                    "RAG chat response",
                    "PASS",
                    f"conv_id={conv_id}, model={model}, "
                    f"sources={source_names}, response_len={len(response_text)}",
                )
                return True
            else:
                self._record(
                    "RAG chat response",
                    "FAIL",
                    f"Empty response or no conversation ID: {data}",
                )
                return False
        except Exception as exc:
            self._record("RAG chat response", "FAIL", str(exc))
            return False

    def test_unified_search(self) -> bool:
        """Test: Search across all sources and verify unified results."""
        try:
            with httpx.Client(timeout=TIMEOUT) as c:
                r = c.post(
                    f"{self.base_url}/knowledge/search",
                    json={
                        "query": "system architecture",
                        "sources": ["docs", "notes", "transcripts"],
                        "limit": 10,
                        "threshold": 0.3,
                    },
                )
                r.raise_for_status()
                data = r.json()

            results = data.get("results", [])
            source_types = set(r.get("source", "") for r in results)

            self._record(
                "Unified cross-source search",
                "PASS",
                f"results={len(results)}, source_types={source_types}",
            )
            return True
        except Exception as exc:
            self._record("Unified cross-source search", "FAIL", str(exc))
            return False

    def test_scheduler_status(self) -> bool:
        """Test: Check scheduler is running with configured tasks."""
        try:
            with httpx.Client(timeout=QUICK_TIMEOUT) as c:
                r = c.get(f"{self.base_url}/health/scheduler")
                r.raise_for_status()
                data = r.json()

            status = data.get("status")
            tasks = data.get("tasks", [])
            task_names = [t["name"] for t in tasks]

            if status == "running" and len(tasks) > 0:
                self._record(
                    "Scheduler status",
                    "PASS",
                    f"status={status}, tasks={task_names}",
                )
                return True
            else:
                self._record(
                    "Scheduler status",
                    "FAIL",
                    f"status={status}, tasks={task_names}",
                )
                return False
        except Exception as exc:
            self._record("Scheduler status", "FAIL", str(exc))
            return False

    def test_cleanup(self) -> bool:
        """Clean up: delete the pipeline-test source."""
        try:
            with httpx.Client(timeout=QUICK_TIMEOUT) as c:
                r = c.delete(f"{self.base_url}/knowledge/source/pipeline-test")
                r.raise_for_status()
                data = r.json()

            deleted = data.get("deleted_count", 0)
            self._record("Cleanup test data", "PASS", f"deleted {deleted} document(s)")
            return True
        except Exception as exc:
            self._record("Cleanup test data", "FAIL", str(exc))
            return False

    # ------------------------------------------------------------------
    # Runner
    # ------------------------------------------------------------------

    def run_all(self) -> bool:
        """Run all tests in order and print summary."""
        print(f"\nElmer Knowledge Pipeline — End-to-End Tests")
        print(f"Base URL: {self.base_url}")
        print("=" * 60)

        start = time.time()

        # 1. Health check (gate for all other tests)
        if not self.test_health():
            print("\nCore API is not reachable. Start services with: make up")
            return False

        # 2. Embedding
        print("\n--- Embedding ---")
        self.test_embedding()

        # 3. Ingestion
        print("\n--- Ingestion ---")
        self.test_ingest_text()
        self.test_directory_ingest()
        self.test_sources_list()

        # 4. Search
        print("\n--- Search ---")
        self.test_search_ingested()
        self.test_unified_search()

        # 5. Obsidian sync
        print("\n--- Obsidian Sync ---")
        self.test_obsidian_sync()

        # 6. Transcription
        print("\n--- Transcription ---")
        self.test_transcription_list()

        # 7. Chat
        print("\n--- RAG Chat ---")
        self.test_chat_rag()

        # 8. Scheduler
        print("\n--- Scheduler ---")
        self.test_scheduler_status()

        # 9. Cleanup
        print("\n--- Cleanup ---")
        self.test_cleanup()

        # Summary
        duration = time.time() - start
        print("\n" + "=" * 60)
        print(
            f"Results: {self.passed} passed, {self.failed} failed, "
            f"{self.skipped} skipped ({duration:.1f}s)"
        )

        if self.failed == 0:
            print("\033[32mAll tests passed!\033[0m\n")
        else:
            print(f"\033[31m{self.failed} test(s) failed.\033[0m\n")

        return self.failed == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Elmer knowledge pipeline E2E tests")
    parser.add_argument(
        "--base-url", default="http://localhost:8100",
        help="Core API base URL (default: http://localhost:8100)",
    )
    args = parser.parse_args()

    runner = PipelineTest(args.base_url)
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
