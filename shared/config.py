"""Shared configuration loading for pipelines.

Provides YAML config loading with a cascading merge strategy:
  pipeline default file → custom file → runtime overrides dict.

Verbose propagation: automatically sets ``verbose`` in each stage config
section so individual stages don't need to be wired manually.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (returns a new dict)."""
    merged = dict(base)
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config(
    default_path: Path,
    config_path: Path | None = None,
    overrides: dict | None = None,
) -> dict:
    """Load pipeline config with fallback chain.

    Priority (highest wins): *overrides* > *config_path* > *default_path*.
    """
    with default_path.open() as f:
        cfg = yaml.safe_load(f) or {}

    if config_path and config_path.resolve() != default_path.resolve():
        with config_path.open() as f:
            custom = yaml.safe_load(f) or {}
        cfg = deep_merge(cfg, custom)

    if overrides:
        cfg = deep_merge(cfg, overrides)

    return cfg


def propagate_verbose(cfg: dict) -> None:
    """Ensure every dict inside ``cfg["stages"]`` has a ``verbose`` key.

    Reads top-level ``cfg["verbose"]`` (defaults to True) and sets it in
    each stage section that doesn't already override it.  Mutates *cfg*
    in place.
    """
    verbose = cfg.get("verbose", True)
    for section in cfg.get("stages", {}).values():
        if isinstance(section, dict):
            section.setdefault("verbose", verbose)
