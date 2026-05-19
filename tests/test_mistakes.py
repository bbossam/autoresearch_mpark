from __future__ import annotations

from autoresearch.mistakes import MistakeLedger


def test_ledger_records_and_persists(tmp_path):
    path = tmp_path / "m.json"
    ledger = MistakeLedger(path)
    ledger.record("r1", "p1", "caching helps", "no improvement", source="analyze")
    ledger.save()

    reloaded = MistakeLedger(path)
    assert len(reloaded.all()) == 1
    assert reloaded.all()[0]["hypothesis"] == "caching helps"


def test_ledger_for_project_filters(tmp_path):
    ledger = MistakeLedger(tmp_path / "m.json")
    ledger.record("r1", "p1", "h1", "bad", source="analyze")
    ledger.record("r2", "p2", "h2", "bad", source="review")

    assert len(ledger.for_project("p1")) == 1


def test_ledger_as_prompt_text(tmp_path):
    ledger = MistakeLedger(tmp_path / "m.json")
    ledger.record("r1", "p1", "caching helps", "no improvement", source="analyze")

    assert "caching helps" in ledger.as_prompt_text("p1")
    assert ledger.as_prompt_text("other") == ""


def test_ledger_dedupes_by_run_id(tmp_path):
    ledger = MistakeLedger(tmp_path / "m.json")
    ledger.record("r1", "p1", "h", "reason1", source="analyze")
    ledger.record("r1", "p1", "h", "reason2", source="review")

    assert len(ledger.all()) == 1
    assert ledger.all()[0]["reason"] == "reason2"
