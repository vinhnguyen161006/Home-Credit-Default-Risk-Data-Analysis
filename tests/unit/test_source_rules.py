"""The two absolute source rules, enforced on every run of the suite.

Ruff ERA catches commented-out code but not prose comments, and no linter flags a
Vietnamese string in code. Both rules are asserted here so a violation fails locally under
make check, not only in CI.

Permitted hash tokens in Python: a shebang on the first line, a type ignore and a noqa
directive. Vietnamese is permitted only in markdown and in YAML note keys, so configs are
not scanned for language.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

from hcr.paths import project_root

PYTHON_SOURCE_DIRS = ("src", "tests", "reports")
NON_PYTHON_FILES_WITHOUT_COMMENTS = (
    "Makefile",
    "pyproject.toml",
    "docker-compose.yml",
    ".env.example",
)
NON_PYTHON_GLOBS_WITHOUT_COMMENTS = ("configs/*.yml", ".github/workflows/*.yml")
LANGUAGE_CHECKED_SUFFIXES = {".py", ".sql"}
PERMITTED_COMMENT = re.compile(r"^#\s*(type:\s*ignore|noqa)\b")
HASH_COMMENT = re.compile(r"(^|\s)#")
EXCLUDED_DIR_NAMES = {"__pycache__", ".ipynb_checkpoints"}


def _files_under(directories: tuple[str, ...], suffixes: set[str]) -> Iterator[Path]:
    root = project_root()
    for directory in directories:
        for path in sorted((root / directory).rglob("*")):
            if path.suffix in suffixes and not EXCLUDED_DIR_NAMES & set(path.parts):
                yield path


def _non_python_files() -> Iterator[Path]:
    root = project_root()
    yield from (root / name for name in NON_PYTHON_FILES_WITHOUT_COMMENTS)
    for pattern in NON_PYTHON_GLOBS_WITHOUT_COMMENTS:
        yield from sorted(root.glob(pattern))


def _forbidden_python_comments(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    violations = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        is_shebang = token.start == (1, 0) and token.string.startswith("#!")
        if not is_shebang and not PERMITTED_COMMENT.match(token.string):
            violations.append(f"{path}:{token.start[0]}: {token.string}")
    return violations


def _non_english_letters(path: Path) -> list[str]:
    violations = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if any(char.isalpha() and not char.isascii() for char in line):
            violations.append(f"{path}:{number}: {line.strip()}")
    return violations


def test_python_files_have_no_hash_comments() -> None:
    violations = [
        violation
        for path in _files_under(PYTHON_SOURCE_DIRS, {".py"})
        for violation in _forbidden_python_comments(path)
    ]

    assert violations == []


def test_config_and_tooling_files_have_no_hash_comments() -> None:
    violations = [
        f"{path}:{number}: {line.strip()}"
        for path in _non_python_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if HASH_COMMENT.search(line)
    ]

    assert violations == []


def test_source_files_have_no_non_english_letters() -> None:
    violations = [
        violation
        for path in _files_under(PYTHON_SOURCE_DIRS, LANGUAGE_CHECKED_SUFFIXES)
        for violation in _non_english_letters(path)
    ]

    assert violations == []
