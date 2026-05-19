"""Rough token accounting for prompts sent to Codex.

No tokenizer dependency — a deliberately conservative character-ratio
heuristic, so the review path can check a prompt fits the available token
budget *before* spending a call on it.
"""

from __future__ import annotations

from dataclasses import dataclass

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Conservative token-count estimate for ``text``."""
    if not text:
        return 0
    return -(-len(text) // CHARS_PER_TOKEN)  # ceil division


def clip_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Trim ``text`` to fit ``max_tokens``, keeping head and tail.

    Returns ``(possibly_clipped_text, was_clipped)``.
    """
    if max_tokens <= 0:
        return "", bool(text)
    if estimate_tokens(text) <= max_tokens:
        return text, False
    half = (max_tokens * CHARS_PER_TOKEN) // 2
    omitted = len(text) - 2 * half
    dropped_tokens = estimate_tokens(text) - max_tokens
    marker = f"\n\n... [{omitted} chars / ~{dropped_tokens} tokens clipped] ...\n\n"
    return text[:half] + marker + text[-half:], True


@dataclass(frozen=True)
class TokenCheck:
    estimated: int
    budget: int

    @property
    def fits(self) -> bool:
        return self.estimated <= self.budget

    @property
    def headroom(self) -> int:
        return self.budget - self.estimated


def check_budget(text: str, budget: int) -> TokenCheck:
    """Estimate ``text`` tokens and compare against an available-token budget."""
    return TokenCheck(estimated=estimate_tokens(text), budget=budget)
