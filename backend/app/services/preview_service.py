import csv
from pathlib import Path
from typing import Any


def read_preview_rows(path: Path, limit: int = 50) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            rows.append(dict(row))
    return rows