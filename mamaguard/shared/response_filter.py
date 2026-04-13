"""
Response post-processor — cleans formatting noise from LLM output.

Strips markdown artifacts that look bad in chat UIs:
  - Excessive horizontal rules (``---``)
  - Triple backticks wrapping non-code content
  - Redundant repeated headers
  - Runs of blank lines

Light touch: only cleans formatting noise, never alters clinical content.
Wired as ``after_model_callback`` on the orchestrator only.
"""

from __future__ import annotations

import re
from typing import Any

from google.adk.models.llm_response import LlmResponse

# ---------------------------------------------------------------------------
# Formatting cleanup rules
# ---------------------------------------------------------------------------

# Collapse 3+ consecutive horizontal rules (---/***/___ with optional spaces)
# into a single one.
_EXCESSIVE_RULES = re.compile(
    r"([ \t]*(?:---+|\*\*\*+|___+)[ \t]*\n){2,}",
)

# Triple-backtick blocks that contain NO code-like content — just prose.
# Heuristic: block has no indentation, no `=`, no `{`, no `(`, no `import`,
# no `def `, no `class `, and is short (≤5 lines).
_FENCED_BLOCK = re.compile(
    r"```[a-z]*\n(.*?)```",
    re.DOTALL,
)

_CODE_SIGNALS = re.compile(
    r"[={}()\[\]]|^\s{4,}\S|^import |^from |^def |^class |^SELECT |^CREATE |"
    r"^curl |^\$ |^pip |^docker |^make |^git |^python",
    re.MULTILINE,
)

# Consecutive duplicate headers (e.g., "## Talk\n## Talk").
_DUPLICATE_HEADER = re.compile(
    r"^(#{1,6}\s+.+)$\n\1$",
    re.MULTILINE,
)

# 3+ consecutive blank lines → 2
_EXCESSIVE_BLANKS = re.compile(r"\n{4,}")

# Leading/trailing horizontal rules at the very start/end of the text
_LEADING_RULE = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*\n+")
_TRAILING_RULE = re.compile(r"\n+\s*(?:---+|\*\*\*+|___+)\s*$")


def _is_prose_block(content: str) -> bool:
    """Return True if a fenced code block contains only prose (no code)."""
    lines = content.strip().split("\n")
    if len(lines) > 5:
        return False
    return _CODE_SIGNALS.search(content) is None


def clean_formatting(text: str) -> str:
    """Remove formatting noise from response text.

    Returns the cleaned text. Never alters clinical content — only touches
    markdown structural artifacts.
    """
    if not text:
        return text

    result = text

    # 1. Strip leading/trailing horizontal rules
    result = _LEADING_RULE.sub("", result)
    result = _TRAILING_RULE.sub("", result)

    # 2. Collapse excessive horizontal rules (3+ → 1)
    result = _EXCESSIVE_RULES.sub("---\n", result)

    # 3. Unwrap fenced blocks that contain only prose
    def _unwrap_prose(m: re.Match) -> str:
        inner = m.group(1)
        if _is_prose_block(inner):
            return inner.strip()
        return m.group(0)

    result = _FENCED_BLOCK.sub(_unwrap_prose, result)

    # 4. Remove duplicate consecutive headers
    result = _DUPLICATE_HEADER.sub(r"\1", result)

    # 5. Collapse excessive blank lines (3+ → 2)
    result = _EXCESSIVE_BLANKS.sub("\n\n\n", result)

    return result


# ---------------------------------------------------------------------------
# ADK after_model_callback
# ---------------------------------------------------------------------------


def response_format_callback(
    callback_context: Any,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Post-model formatting cleanup.

    Scans text parts of the LLM response and removes formatting noise.
    Returns None (keeps the mutated original) in all cases.
    """
    content = llm_response.content
    if content is None or content.parts is None:
        return None

    for part in content.parts:
        if part.text is None:
            continue
        part.text = clean_formatting(part.text)

    return None
