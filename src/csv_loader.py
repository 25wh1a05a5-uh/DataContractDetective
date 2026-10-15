"""Load CSV data for DataContract Detective."""

from pathlib import Path
import pandas as pd


def load_csv(file_path):
    """Load a CSV file and return its data and basic metadata."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    if path.suffix.lower() != ".csv":
        raise ValueError("The input file must be a CSV file.")

    data = pd.read_csv(path)

    return {
        "file_name": path.name,
        "row_count": len(data),
        "columns": list(data.columns),
        "data": data,
    }