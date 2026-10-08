"""Keep committed result records text-only and free of private artifact paths."""

import json
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MIN_RESULT_FILES = 28
MAX_FILE_BYTES = 64 * 1024
MAX_STRING_LENGTH = 2000
BASE64_RUN = re.compile(r"[A-Za-z0-9+/=]{200,}")
FORBIDDEN_SEGMENTS = {"clips", "frames", "images", "pairs", "renders", "video"}
FORBIDDEN_PATH = re.compile(
    r"(?:^|[\\/])(?:clips|frames|images|pairs|renders|video)(?:[\\/]|$)", re.IGNORECASE
)
LOCAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/mnt/c/|/home/)", re.IGNORECASE)


def _strings(value, pointer: str = "$"):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, f"{pointer}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{pointer}.{key}")


def _assert_private_results(root: Path, minimum_files: int = MIN_RESULT_FILES) -> None:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    assert len(files) >= minimum_files, (
        f"walked {len(files)} result files, expected at least {minimum_files}"
    )

    for path in files:
        relative = path.relative_to(root)
        assert not path.is_symlink(), f"result must not be a symlink: {relative}"
        assert path.name == "README.md" or path.suffix == ".json", (
            f"result must be JSON or README.md: {relative}"
        )
        assert path.stat().st_size < MAX_FILE_BYTES, f"result is 64 KB or larger: {relative}"
        assert not (FORBIDDEN_SEGMENTS & {part.lower() for part in relative.parts}), (
            f"result path has a forbidden segment: {relative}"
        )

        text = path.read_text(encoding="utf-8")
        assert BASE64_RUN.search(text) is None, f"base64-looking run in {relative}"
        assert FORBIDDEN_PATH.search(text) is None, f"forbidden artifact path in {relative}"
        assert LOCAL_PATH.search(text) is None, f"absolute local path in {relative}"

        if path.suffix != ".json":
            assert all(len(line) <= MAX_STRING_LENGTH for line in text.splitlines()), (
                f"text line over {MAX_STRING_LENGTH} characters in {relative}"
            )
            continue

        data = json.loads(text)
        for pointer, value in _strings(data):
            assert len(value) <= MAX_STRING_LENGTH, (
                f"string over {MAX_STRING_LENGTH} characters at {relative}:{pointer}"
            )


def test_results_obey_take_record_privacy_contract() -> None:
    _assert_private_results(RESULTS)


def test_privacy_guard_rejects_planted_base64_in_temporary_copy(tmp_path: Path) -> None:
    copied_results = tmp_path / "results"
    shutil.copytree(RESULTS, copied_results)
    planted = copied_results / "planted.json"
    planted.write_text(json.dumps({"payload": "A" * 200}), encoding="utf-8")

    with pytest.raises(AssertionError, match="base64-looking run"):
        _assert_private_results(copied_results)
