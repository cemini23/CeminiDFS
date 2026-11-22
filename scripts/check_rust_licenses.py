#!/usr/bin/env python3
"""Fail unless every resolved crate license is on the allowlist."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "rust" / "sim_kernel" / "Cargo.toml"
ALLOWED = frozenset(
    {
        "MIT",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "Unicode-3.0",
    }
)
TOKEN = re.compile(r"\(|\)|OR|AND|[A-Za-z0-9][A-Za-z0-9.+-]*")


class LicenseParseError(ValueError):
    """The license expression is empty or not valid SPDX-style text."""


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.index = 0

    def peek(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def eat(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None:
            raise LicenseParseError("license expression ended early")
        if expected is not None and token != expected:
            raise LicenseParseError(f"expected {expected}, found {token}")
        self.index += 1
        return token

    def parse(self) -> bool:
        allowed = self.parse_or()
        if self.peek() is not None:
            raise LicenseParseError("trailing license tokens")
        return allowed

    def parse_or(self) -> bool:
        allowed = self.parse_and()
        while self.peek() == "OR":
            self.eat("OR")
            right = self.parse_and()
            allowed = allowed or right
        return allowed

    def parse_and(self) -> bool:
        allowed = self.parse_atom()
        while self.peek() == "AND":
            self.eat("AND")
            right = self.parse_atom()
            allowed = allowed and right
        return allowed

    def parse_atom(self) -> bool:
        if self.peek() == "(":
            self.eat("(")
            allowed = self.parse_or()
            self.eat(")")
            return allowed
        token = self.eat()
        if token in {"OR", "AND", "WITH", ")"}:
            raise LicenseParseError(f"unexpected token {token}")
        if self.peek() == "WITH":
            # An SPDX exception adds permissions. The base license must be allowed.
            self.eat("WITH")
            exception = self.eat()
            if exception in {"OR", "AND", "WITH", "(", ")"}:
                raise LicenseParseError(f"unexpected exception {exception}")
        return token in ALLOWED


def license_allowed(expression: str | None) -> bool:
    """Return True when one allowed reading of the SPDX expression exists."""

    if not expression or not expression.strip():
        return False
    normalized = expression.replace("/", " OR ")
    tokens = TOKEN.findall(normalized)
    if not tokens:
        return False
    consumed = re.sub(r"\s+", "", TOKEN.sub("", normalized))
    if consumed:
        return False
    try:
        return _Parser(tokens).parse()
    except LicenseParseError:
        return False


def main() -> int:
    completed = subprocess.run(
        [
            "cargo",
            "metadata",
            "--format-version",
            "1",
            "--manifest-path",
            str(MANIFEST),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        return completed.returncode

    metadata = json.loads(completed.stdout)
    blocked: list[str] = []
    for package in metadata.get("packages", []):
        name = str(package.get("name", ""))
        version = str(package.get("version", ""))
        expression = package.get("license")
        text = expression if isinstance(expression, str) else ""
        if license_allowed(text):
            print(f"ok {name} {version} {text}")
            continue
        shown = text or "<missing>"
        blocked.append(f"{name} {version} {shown}")

    if blocked:
        for row in blocked:
            print(f"blocked {row}", file=sys.stderr)
        return 1
    print(f"checked {len(metadata.get('packages', []))} packages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
