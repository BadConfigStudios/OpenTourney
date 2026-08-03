#!/usr/bin/env python3
import json
from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "docs" / "openapi.json"


def main() -> None:
    spec = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
