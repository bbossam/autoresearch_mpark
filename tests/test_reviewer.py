from __future__ import annotations

from autoresearch.agents import ReviewAgent, ReviewArtifacts


def _artifacts() -> ReviewArtifacts:
    return ReviewArtifacts(
        run_id="r1",
        hypothesis="caching helps",
        primary_metric="score",
        metrics={"score": 0.9},
        log_excerpt="training ok",
    )


def test_review_keeps_a_good_run():
    outcome = ReviewAgent().review(
        _artifacts(),
        lambda p: '{"verdict":"keep","interesting":true,"summary":"solid win","issues":[]}',
    )

    assert outcome.ok
    assert outcome.data["verdict"] == "keep"


def test_review_handles_code_fenced_json():
    outcome = ReviewAgent().review(
        _artifacts(),
        lambda p: '```json\n{"verdict":"discard","summary":"broken","issues":["nan loss"]}\n```',
    )

    assert outcome.data["verdict"] == "discard"
    assert "nan loss" in outcome.issues


def test_review_flags_unparseable_output():
    outcome = ReviewAgent().review(_artifacts(), lambda p: "no json here, just prose")

    assert not outcome.ok
    assert outcome.data["verdict"] == "flag"


def test_build_prompt_contains_run_context():
    prompt = ReviewAgent().build_prompt(_artifacts())

    assert "r1" in prompt
    assert "caching helps" in prompt
