# tests/test_strategy_registry.py
import pandas as pd
import pytest
from pathlib import Path


def test_discover_strategies_finds_baker_bros(monkeypatch, tmp_path):
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    assert len(strategies) >= 1
    modules = [s["module"] for s in strategies]
    assert "baker_bros_top10_ew" in modules


def test_discovered_strategy_has_required_keys(monkeypatch, tmp_path):
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    for s in strategies:
        assert "name" in s
        assert "module" in s
        assert "status" in s
        assert "parameters" in s
        assert callable(s["generate_targets"])


def test_default_status_is_research(monkeypatch, tmp_path):
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    assert all(s["status"] == "Research" for s in strategies)


def test_set_live_updates_status(monkeypatch, tmp_path):
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    module = strategies[0]["module"]
    sr.set_live(module)
    updated = sr.discover_strategies()
    live = [s for s in updated if s["status"] == "Live"]
    assert len(live) == 1
    assert live[0]["module"] == module


def test_set_live_demotes_previous(monkeypatch, tmp_path):
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    pd.DataFrame([
        {"module_name": "strat_a", "status": "Live"},
        {"module_name": "strat_b", "status": "Research"},
    ]).to_csv(tmp_path / "strategy_registry.csv", index=False)
    sr.set_live("strat_b")
    df = pd.read_csv(tmp_path / "strategy_registry.csv")
    assert df[df["module_name"] == "strat_b"].iloc[0]["status"] == "Live"
    assert df[df["module_name"] == "strat_a"].iloc[0]["status"] == "Research"


def test_get_live_strategy_returns_none_when_all_research(monkeypatch, tmp_path):
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    result = sr.get_live_strategy()
    assert result is None


def test_get_live_strategy_returns_live_one(monkeypatch, tmp_path):
    import utils.strategy_registry as sr
    monkeypatch.setattr(sr, "REGISTRY_CSV", tmp_path / "strategy_registry.csv")
    strategies = sr.discover_strategies()
    module = strategies[0]["module"]
    sr.set_live(module)
    result = sr.get_live_strategy()
    assert result is not None
    assert result["module"] == module
