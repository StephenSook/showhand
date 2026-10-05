import hashlib
import json

import pytest

from tools.cosmos_job.validate_result import (
    CONTAINER_IMAGE_DIGEST,
    MODEL_ID,
    MODEL_REVISION,
    validate,
)


def _manifest() -> bytes:
    return json.dumps(
        {
            "windows": [
                {
                    "window_index": 0,
                    "start_s": 0.0,
                    "end_s": 1.0,
                    "pair_path": "window-000.jpg",
                }
            ]
        }
    ).encode()


def _result(manifest: bytes) -> dict:
    return {
        "take_id": "take-1",
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "container_image_digest": CONTAINER_IMAGE_DIGEST,
        "precision": "bfloat16",
        "verdicts": [
            {
                "window_index": 0,
                "start_s": 0.0,
                "end_s": 1.0,
                "raw_output": "<answer>{}</answer>",
            }
        ],
    }


def test_cosmos_result_requires_terminal_success_and_matching_manifest() -> None:
    manifest = _manifest()
    validate({"status": {"state": "SUCCEEDED"}}, _result(manifest), manifest, "take-1")


def test_cosmos_result_rejects_nonterminal_job() -> None:
    manifest = _manifest()
    with pytest.raises(ValueError, match="not SUCCEEDED"):
        validate({"status": {"state": "RUNNING"}}, _result(manifest), manifest, "take-1")
