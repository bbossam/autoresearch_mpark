from __future__ import annotations

from autoresearch.agents import ContextAgent, SessionSnapshot


def test_brief_reports_a_clean_session():
    outcome = ContextAgent().brief(SessionSnapshot(contracts=["r1"], results=["r1"]))

    assert outcome.ok
    assert "session briefing" in outcome.data["briefing"].lower()


def test_brief_flags_hung_runs():
    snapshot = SessionSnapshot(statuses=[{"run_id": "r1", "state": "stalled"}])
    outcome = ContextAgent().brief(snapshot)

    assert not outcome.ok
    assert outcome.data["hung"] == ["r1"]


def test_brief_lists_pending_ideas_and_mistakes():
    snapshot = SessionSnapshot(
        pending_ideas=["idea-x"],
        mistakes=[{"hypothesis": "caching helps", "reason": "no improvement"}],
    )
    briefing = ContextAgent().brief(snapshot).data["briefing"]

    assert "idea-x" in briefing
    assert "caching helps" in briefing
