from __future__ import annotations

import json

from autoresearch.agents import ResearchAgent, ResearchContext
from autoresearch.models import IdeaSpec


def _ctx() -> ResearchContext:
    return ResearchContext(
        project_id="p1",
        project_name="P1",
        description="early stage",
        existing_idea_ids=["old-idea"],
    )


def test_hypothesize_parses_ideas():
    payload = json.dumps(
        [
            {"idea_id": "speed-up", "hypothesis": "caching helps", "primary_metric": "score"},
            {"idea_id": "prune", "hypothesis": "pruning helps", "primary_metric": "score"},
        ]
    )
    ideas, outcome = ResearchAgent().hypothesize(_ctx(), lambda p: payload, count=2)

    assert outcome.ok
    assert len(ideas) == 2
    assert all(isinstance(i, IdeaSpec) for i in ideas)
    assert ideas[0].target_project == "p1"


def test_hypothesize_skips_ideas_missing_metric():
    payload = json.dumps(
        [
            {"idea_id": "ok", "hypothesis": "h", "primary_metric": "score"},
            {"idea_id": "bad", "hypothesis": "h2"},
        ]
    )
    ideas, outcome = ResearchAgent().hypothesize(_ctx(), lambda p: payload)

    assert len(ideas) == 1
    assert outcome.issues  # the metric-less idea was skipped


def test_hypothesize_deduplicates_against_existing_ids():
    payload = json.dumps(
        [{"idea_id": "old-idea", "hypothesis": "h", "primary_metric": "score"}]
    )
    ideas, _ = ResearchAgent().hypothesize(_ctx(), lambda p: payload)

    assert ideas[0].idea_id != "old-idea"


def test_hypothesize_flags_unparseable_output():
    ideas, outcome = ResearchAgent().hypothesize(_ctx(), lambda p: "not json at all")

    assert ideas == []
    assert not outcome.ok


def test_hypothesize_builds_accept_rules():
    payload = json.dumps(
        [
            {
                "idea_id": "x",
                "hypothesis": "h",
                "primary_metric": "psnr",
                "accept_operator": "gt",
                "accept_threshold": 27.5,
            }
        ]
    )
    ideas, _ = ResearchAgent().hypothesize(_ctx(), lambda p: payload)

    assert ideas[0].accept_rules
    assert ideas[0].accept_rules[0].metric == "psnr"
    assert ideas[0].accept_rules[0].threshold == 27.5
