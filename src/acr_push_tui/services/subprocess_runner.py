"Subprocess helpers for CLI integrations."

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

logger = logging.getLogger(__name__)


class CommandError(RuntimeError):
    """Raised when a command execution fails."""


@dataclass(frozen=True)
class CommandResult:
    """Result of a CLI command execution."""

    stdout: str
    stderr: str
    return_code: int


def run_command(
    args: Sequence[str],
    check: bool = True,
    on_output: Callable[[str], None] | None = None,
) -> CommandResult:
    """Run a CLI command and capture output.

    Args:
        args: Command arguments.
        check: Whether to raise on non-zero exit.

    Returns:
        CommandResult with stdout, stderr, and return code.

    Raises:
        CommandError: If command fails and check is True.
    """
    logger.debug("Running command: %s", " ".join(args))
    process = subprocess.Popen(
        list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_lines: list[str] = []
    if process.stdout:
        for line in process.stdout:
            clean = line.rstrip("\n")
            output_lines.append(clean)
            if on_output:
                on_output(clean)
    process.wait()
    stdout = "\n".join(output_lines).strip()
    result = CommandResult(stdout=stdout, stderr="", return_code=process.returncode)
    if check and process.returncode != 0:
        raise CommandError(result.stdout or "Command failed.")
    return result
