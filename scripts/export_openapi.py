from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("APP_OTEL_ENABLED", "false")

from app.main import create_app  # noqa: E402


def main() -> None:
    output_path = REPO_ROOT / "openapi" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = create_app().openapi()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
