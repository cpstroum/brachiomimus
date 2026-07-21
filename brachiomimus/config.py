"""
config.py — user-tunable settings for dance.py and reach.py, sourced from the environment.

Values come from (highest priority first):
  1. a real environment variable (e.g. `BRACHIOMIMUS_PORT=COM4 python -m demos.dance`)
  2. a `.env` file at the repository root (KEY=VALUE lines)
  3. the built-in defaults below

CLI flags on the demos still win over all of these — the env/.env layer just
sets the defaults so you don't have to retype your arm's calibration every run.

The committed template is `.env.example`; copy it to `.env` (which is
gitignored) and fill in your values. Because `.env` is never committed, it may
also hold real secrets — e.g. `WANDB_API_KEY`, which cloud training reads via
`hf jobs run --secrets-file .env`.
"""

import os
from pathlib import Path

# .env lives at the repository root; this module sits one level down in the
# brachiomimus/ package, hence parent.parent.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE loader so we don't need python-dotenv. Existing real
    environment variables are left untouched (they take precedence)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(_ENV_PATH)


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    try:
        return float(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str | None) -> str | None:
    value = os.environ.get(name, "")
    return value or default


# --- Gripper calibration (degrees) --------------------------------------
# The gripper's calibrated zero is not necessarily its closed position, so
# these are per-arm. Find yours with `python dance.py --read-gripper`.
GRIPPER_CLOSED_DEG = _get_float("BRACHIOMIMUS_GRIPPER_CLOSED_DEG", 0.0)
GRIPPER_OPEN_DEG = _get_float("BRACHIOMIMUS_GRIPPER_OPEN_DEG", 45.0)

# --- Optional defaults for common flags ---------------------------------
PORT = _get_str("BRACHIOMIMUS_PORT", "/dev/ttyUSB0")
SENSITIVITY = _get_float("BRACHIOMIMUS_SENSITIVITY", 1.8)
INTENSITY = _get_float("BRACHIOMIMUS_INTENSITY", 1.0)
