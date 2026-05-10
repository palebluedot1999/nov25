# utils/strategy_registry.py
import importlib.util
import pandas as pd
from pathlib import Path

STRATEGIES_DIR = Path(__file__).parent.parent / "strategies"
REGISTRY_CSV = Path(__file__).parent.parent / "data" / "strategy_registry.csv"


def _load_registry() -> pd.DataFrame:
    if not REGISTRY_CSV.exists():
        return pd.DataFrame(columns=["module_name", "status"])
    return pd.read_csv(REGISTRY_CSV)


def _save_registry(df: pd.DataFrame) -> None:
    REGISTRY_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(REGISTRY_CSV, index=False)


def _get_status(module_name: str) -> str:
    df = _load_registry()
    row = df[df["module_name"] == module_name]
    return str(row.iloc[0]["status"]) if not row.empty else "Research"


def _set_status(module_name: str, status: str) -> None:
    df = _load_registry()
    if module_name in df["module_name"].values:
        df.loc[df["module_name"] == module_name, "status"] = status
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"module_name": module_name, "status": status}])],
            ignore_index=True,
        )
    _save_registry(df)


def discover_strategies() -> list[dict]:
    """Return list of strategy config dicts from strategies/ directory."""
    configs = []
    for path in sorted(STRATEGIES_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "STRATEGY_CONFIG"):
                continue
            config = mod.STRATEGY_CONFIG.copy()
            config["module"] = path.stem
            config["status"] = _get_status(path.stem)
            config["generate_targets"] = mod.generate_targets
            configs.append(config)
        except Exception as e:
            import logging
            logging.warning("Failed to load strategy %s: %s", path.stem, e)
            continue
    return configs


def set_live(module_name: str) -> None:
    """Set one strategy as Live; demote all others to Research."""
    df = _load_registry()
    df["status"] = "Research"
    _save_registry(df)
    _set_status(module_name, "Live")


def get_live_strategy() -> dict | None:
    """Return the Live strategy config dict, or None."""
    strategies = discover_strategies()
    live = [s for s in strategies if s["status"] == "Live"]
    return live[0] if live else None
