from __future__ import annotations

import re
from pathlib import Path

DOCKERFILE = Path("Dockerfile")


def main() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    instructions = _instructions(text)
    errors: list[str] = []

    from_instruction = _first_instruction(instructions, "FROM")
    if from_instruction is None:
        errors.append("Dockerfile must define a base image with FROM.")
    elif ":latest" in from_instruction.lower():
        errors.append("Dockerfile base image must not use the latest tag.")

    if not _has_instruction(instructions, "USER", "app"):
        errors.append("Dockerfile must switch to the non-root app user.")

    if not re.search(r"^\s*RUN\s+.*pip install .*--no-cache-dir", text, re.MULTILINE | re.DOTALL):
        errors.append("Dockerfile pip installs must use --no-cache-dir.")

    if not _has_exec_form_command(instructions, "CMD"):
        errors.append("Dockerfile must use exec-form CMD.")

    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)

    print("Dockerfile policy checks passed")


def _instructions(text: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if current:
            current = f"{current} {stripped.removesuffix('\\').strip()}"
        else:
            current = stripped.removesuffix("\\").strip()
        if not stripped.endswith("\\"):
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines


def _first_instruction(instructions: list[str], name: str) -> str | None:
    prefix = f"{name} "
    for instruction in instructions:
        if instruction.upper().startswith(prefix):
            return instruction
    return None


def _has_instruction(instructions: list[str], name: str, value: str) -> bool:
    expected = f"{name} {value}".upper()
    return any(instruction.upper() == expected for instruction in instructions)


def _has_exec_form_command(instructions: list[str], name: str) -> bool:
    prefix = f"{name} "
    for instruction in instructions:
        if instruction.upper().startswith(prefix):
            return instruction[len(prefix) :].strip().startswith("[")
    return False


if __name__ == "__main__":
    main()
