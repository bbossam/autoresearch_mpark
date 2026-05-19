from __future__ import annotations

from autoresearch.tokens import check_budget, clip_to_tokens, estimate_tokens


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100


def test_clip_to_tokens_keeps_short_text():
    clipped, was_clipped = clip_to_tokens("short", 100)

    assert not was_clipped
    assert clipped == "short"


def test_clip_to_tokens_trims_long_text():
    clipped, was_clipped = clip_to_tokens("x" * 10000, 100)

    assert was_clipped
    assert estimate_tokens(clipped) <= 300  # head + tail + marker, bounded


def test_check_budget_flags_oversized_text():
    check = check_budget("a" * 400, budget=50)

    assert not check.fits
    assert check.estimated == 100
    assert check.headroom == -50
