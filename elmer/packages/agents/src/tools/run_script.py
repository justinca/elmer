"""Run script tool — executes scripts from an allowed directory."""

import asyncio
import logging
import os
import shlex
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger("elmer.agents.tools.run_script")

_SCRIPT_TIMEOUT = 30.0
_MAX_OUTPUT = 10_000  # 10 KB per stream


class RunScriptTool(BaseTool):
    name = "run_script"
    description = "Execute a script from the allowed scripts directory."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Script filename to execute",
                },
                "args": {
                    "type": "string",
                    "description": "Space-separated arguments for the script",
                },
            },
            "required": ["script"],
        }

    async def execute(self, arguments: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        script_name = arguments.get("script", "")
        args_str = arguments.get("args", "")

        if not script_name:
            return ToolResult(success=False, error="No script specified")

        scripts_dir = Path(
            self.config.get(
                "scripts_dir",
                getattr(context.get("settings"), "AGENT_SCRIPTS_DIR", "/app/agent-scripts"),
            )
        )

        # Resolve the full path and prevent traversal.
        script_path = (scripts_dir / script_name).resolve()
        if not str(script_path).startswith(str(scripts_dir.resolve())):
            return ToolResult(success=False, error="Path traversal not allowed")

        if not script_path.exists():
            return ToolResult(success=False, error=f"Script not found: {script_name}")

        if not os.access(script_path, os.X_OK):
            return ToolResult(success=False, error=f"Script not executable: {script_name}")

        # Build command.
        cmd = [str(script_path)]
        if args_str.strip():
            cmd.extend(shlex.split(args_str))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(scripts_dir),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=_SCRIPT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(success=False, error=f"Script timed out after {_SCRIPT_TIMEOUT}s")

            stdout = stdout_bytes.decode(errors="replace")[:_MAX_OUTPUT]
            stderr = stderr_bytes.decode(errors="replace")[:_MAX_OUTPUT]

            return ToolResult(
                success=proc.returncode == 0,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": proc.returncode,
                },
                error=stderr if proc.returncode != 0 else None,
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Script execution failed: {exc}")
