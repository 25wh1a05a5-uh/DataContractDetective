
"""Verify whether an investigation's input CSV has changed."""

import json
import sys
from pathlib import Path

from replay_record import calculate_file_sha256


def verify_replay(replay_file, input_file):
    """Compare the current input fingerprint with the saved fingerprint."""

    replay_path = Path(replay_file)
    input_path = Path(input_file)

    if not replay_path.is_file():
        raise FileNotFoundError(
            f"Replay record not found: {replay_path}"
        )

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Input CSV not found: {input_path}"
        )

    record = json.loads(replay_path.read_text(encoding="utf-8"))

    expected_hash = record.get("input_sha256")

    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError("Replay record has no valid SHA-256 fingerprint.")

    actual_hash = calculate_file_sha256(input_path)
    matches = actual_hash == expected_hash

    return {
        "investigation_id": record.get("investigation_id"),
        "recorded_input": record.get("input_file"),
        "current_input": input_path.name,
        "expected_sha256": expected_hash,
        "actual_sha256": actual_hash,
        "input_unchanged": matches,
        "status": "MATCH" if matches else "CHANGED",
    }


def main():
    project_dir = Path(__file__).resolve().parent.parent

    if len(sys.argv) != 3:
        print(
            "Usage: python .\\src\\verify_replay.py "
            "<replay_record.json> <input.csv>"
        )
        sys.exit(2)

    replay_file = Path(sys.argv[1])
    input_file = Path(sys.argv[2])

    if not replay_file.is_absolute():
        replay_file = Path.cwd() / replay_file

    if not input_file.is_absolute():
        input_file = Path.cwd() / input_file

    try:
        result = verify_replay(replay_file, input_file)

        print("Replay Verification")
        print("-------------------")
        print(f"Investigation ID: {result['investigation_id']}")
        print(f"Recorded input: {result['recorded_input']}")
        print(f"Current input: {result['current_input']}")
        print(f"Verification status: {result['status']}")
        print(f"Input unchanged: {result['input_unchanged']}")

        if result["input_unchanged"]:
            print("The CSV contents match the saved fingerprint.")
        else:
            print("The CSV contents differ from the saved fingerprint.")

    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"Verification failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()

