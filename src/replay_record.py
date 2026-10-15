
"""Create reproducible metadata for a CSV investigation."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def calculate_file_sha256(file_path: str | Path) -> str:
    """Return the SHA-256 fingerprint of a file's contents."""

    path = Path(file_path)
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def create_replay_record(
    file_path: str | Path,
    configuration: dict[str, Any],
    checks_performed: list[str],
) -> dict[str, Any]:
    """Record the input fingerprint and settings used for an investigation."""

    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    if not isinstance(configuration, dict):
        raise TypeError("Configuration must be a dictionary.")

    if not isinstance(checks_performed, list):
        raise TypeError("Checks performed must be a list.")

    if any(
        not isinstance(check, str) or not check.strip()
        for check in checks_performed
    ):
        raise ValueError("Each check name must be a non-empty string.")

    return {
        "investigation_id": str(uuid.uuid4()),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": path.name,
        "input_sha256": calculate_file_sha256(path),
        "configuration": configuration.copy(),
        "checks_performed": checks_performed.copy(),
        "replay_note": (
            "The fingerprint identifies the input file contents. "
            "Reproducing results also requires the same configuration, "
            "code version, and execution environment."
        ),
    }


def save_replay_record(
    record: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Save replay metadata as a JSON file."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, indent=2, default=str),
        encoding="utf-8",
    )

    return path
