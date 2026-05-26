from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.auth import create_demo_jwt  # noqa: E402
from app.core.config import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local demo JWT for the service.")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--expires-minutes", type=int, default=60)
    args = parser.parse_args()

    token = create_demo_jwt(
        settings=get_settings(),
        tenant_id=args.tenant_id,
        subject=args.subject,
        scopes=tuple(args.scope),
        expires_delta=timedelta(minutes=args.expires_minutes),
    )
    print(token)


if __name__ == "__main__":
    main()
