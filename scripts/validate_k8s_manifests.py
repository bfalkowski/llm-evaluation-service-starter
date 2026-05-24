from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

MANIFEST_DIR = Path("deploy/k8s")
REQUIRED_FIELDS = ("apiVersion", "kind", "metadata")


def main() -> None:
    manifest_paths = sorted(MANIFEST_DIR.glob("*.yaml"))
    if not manifest_paths:
        raise SystemExit(f"No Kubernetes manifests found in {MANIFEST_DIR}")

    errors: list[str] = []
    resource_count = 0

    for path in manifest_paths:
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            errors.append(f"{path}: invalid YAML: {exc}")
            continue

        for index, document in enumerate(documents, start=1):
            if document is None:
                continue

            resource_count += 1
            errors.extend(_validate_document(path, index, document))

    if resource_count == 0:
        errors.append(f"No Kubernetes resources found in {MANIFEST_DIR}")

    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)

    print(f"Validated {resource_count} Kubernetes resources in {MANIFEST_DIR}")


def _validate_document(path: Path, index: int, document: Any) -> list[str]:
    location = f"{path} document {index}"
    errors: list[str] = []

    if not isinstance(document, dict):
        return [f"{location}: expected a mapping"]

    for field in REQUIRED_FIELDS:
        if not document.get(field):
            errors.append(f"{location}: missing {field}")

    metadata = document.get("metadata")
    if not isinstance(metadata, dict):
        errors.append(f"{location}: metadata must be a mapping")
    elif not metadata.get("name"):
        errors.append(f"{location}: missing metadata.name")

    return errors


if __name__ == "__main__":
    main()
