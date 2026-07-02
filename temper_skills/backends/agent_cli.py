"""AgentCliBackend — the subscription path: drive a headless agent CLI.

Routes each turn through `claude -p` or `opencode run` (or a custom command),
which run on the user's existing subscription login. These CLIs have no native
structured-output mode, so the JSON Schema is embedded in the prompt and the
result is scraped + validated, with one corrective retry.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from .base import Backend

T = TypeVar("T", bound=BaseModel)

DEFAULT_TIMEOUT = 300  # agent CLIs can take a while per turn


def _qualify_opencode_model(model: str) -> str:
    return model if "/" in model else f"anthropic/{model}"


# preset -> (argv builder, stdout->assistant-text extractor)
def _claude_argv(prompt: str, model: str) -> list[str]:
    return ["claude", "-p", prompt, "--model", model, "--output-format", "json"]


def _claude_text(stdout: str) -> str:
    # `--output-format json` wraps the reply; the assistant text is in .result
    return json.loads(stdout).get("result", stdout)


def _opencode_argv(prompt: str, model: str) -> list[str]:
    return ["opencode", "run", prompt, "-m", _qualify_opencode_model(model)]


def _opencode_text(stdout: str) -> str:
    return stdout


PRESETS: dict[str, tuple[Callable[[str, str], list[str]], Callable[[str], str]]] = {
    "claude": (_claude_argv, _claude_text),
    "opencode": (_opencode_argv, _opencode_text),
}


def _extract_json(text: str) -> str | None:
    """Pull the first balanced top-level JSON object out of arbitrary CLI output."""
    # Drop markdown code fences if present.
    if "```" in text:
        parts = text.split("```")
        # the content right after a ```/```json fence is the most likely payload
        for i in range(1, len(parts), 2):
            seg = parts[i]
            if seg.lstrip().startswith("json"):
                seg = seg.lstrip()[4:]
            if "{" in seg:
                text = seg
                break
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


class AgentCliBackend(Backend):
    def __init__(self, preset: str = "opencode", model: str = "claude-sonnet-4-6",
                 timeout: int = DEFAULT_TIMEOUT):
        super().__init__(model)
        if preset not in PRESETS:
            raise ValueError(f"unknown agent-CLI preset {preset!r}; choose from {list(PRESETS)}")
        self.name = preset
        self._build_argv, self._extract_text = PRESETS[preset]
        self.timeout = timeout

    def _run(self, prompt: str) -> str:
        argv = self._build_argv(prompt, self.model)
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"{self.name} CLI exited {proc.returncode}: {proc.stderr.strip()[:500]}"
            )
        return self._extract_text(proc.stdout)

    def complete(self, system: str, user: str, schema: type[T]) -> T:
        base = (
            f"{system}\n\n{user}\n\n"
            "Return ONLY a JSON object matching this JSON Schema — no prose, no "
            "markdown fence:\n" + json.dumps(schema.model_json_schema())
        )
        prompt = base
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                text = self._run(prompt)
            except (subprocess.TimeoutExpired, RuntimeError) as e:
                # A timed-out or transiently failing CLI call gets the same single
                # retry as invalid JSON — a slow turn must not bypass the retry path.
                last_err = e
                continue
            blob = _extract_json(text)
            if blob is not None:
                try:
                    return schema.model_validate_json(blob)
                except ValidationError as e:
                    last_err = e
            else:
                last_err = ValueError("no JSON object found in CLI output")
            prompt = base + (
                "\n\nYour previous output was not valid JSON for the schema. "
                "Return ONLY the JSON object, nothing else."
            )
        raise RuntimeError(f"{self.name} CLI did not return schema-valid JSON: {last_err}")


def cli_runs(binary: str) -> bool:
    """True if the binary is on PATH and `--version` runs without crashing.

    Guards against an installed-but-broken CLI (e.g. claude on an incompatible
    Node), so auto-detection can skip it.
    """
    if shutil.which(binary) is None:
        return False
    try:
        proc = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False
