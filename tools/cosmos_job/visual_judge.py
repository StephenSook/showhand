#!/usr/bin/env python3
"""Run the fixed per-window Showhand visual question through Cosmos Reason1."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import torch
from qwen_vl_utils import process_vision_info
from transformers import AutoModelForMultimodalLM, AutoProcessor

MODEL_ID = "nvidia/Cosmos-Reason1-7B"
REASON_CODES = {
    "upper_body_pose",
    "lower_body_pose",
    "timing",
    "orientation",
    "occlusion",
    "insufficient_view",
}
FIXED_QUESTION = (
    "The left image is the human demonstration and the right image is the simulated Unitree G1. "
    "For this one-second window, does the robot's pose match the human's? Judge pose and timing, "
    "not appearance. Return one JSON object with exactly these keys: match (boolean), "
    "reason_codes (an array using only upper_body_pose, lower_body_pose, timing, orientation, "
    "occlusion, insufficient_view), and summary (a short string). A match must have an empty "
    "reason_codes array. A mismatch must have at least one reason code."
)


def _parse_object(raw: str) -> dict:
    answer_match = re.search(r"<answer>\s*(.*?)\s*</answer>", raw, flags=re.DOTALL)
    candidate = answer_match.group(1) if answer_match else raw
    start = candidate.find("{")
    if start < 0:
        raise ValueError("Cosmos output contains no JSON object")
    value, _ = json.JSONDecoder().raw_decode(candidate[start:])
    if not isinstance(value, dict):
        raise ValueError("Cosmos structured output is not an object")
    expected = {"match", "reason_codes", "summary"}
    if set(value) != expected:
        raise ValueError(f"Cosmos output keys differ from schema: {sorted(value)}")
    if not isinstance(value["match"], bool):
        raise ValueError("Cosmos match is not a boolean")
    if not isinstance(value["reason_codes"], list):
        raise ValueError("Cosmos reason_codes is not a list")
    unknown = set(value["reason_codes"]).difference(REASON_CODES)
    if unknown:
        raise ValueError(f"Cosmos returned unknown reason codes: {sorted(unknown)}")
    if value["match"] and value["reason_codes"]:
        raise ValueError("Cosmos match carries mismatch reason codes")
    if not value["match"] and not value["reason_codes"]:
        raise ValueError("Cosmos mismatch has no reason code")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("Cosmos summary is empty")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", default=4096, type=int)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    windows = manifest.get("windows")
    if not isinstance(windows, list) or not windows:
        raise ValueError("visual manifest contains no windows")

    load_started = time.perf_counter()
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForMultimodalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    load_s = time.perf_counter() - load_started
    verdicts = []
    for expected_index, window in enumerate(windows):
        if int(window["window_index"]) != expected_index:
            raise ValueError("visual manifest window indexes are not contiguous")
        image_path = Path(window["pair_path"])
        if not image_path.is_absolute():
            image_path = manifest_path.parent / image_path
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(image_path)},
                    {"type": "text", "text": FIXED_QUESTION},
                ],
            }
        ]
        prompt = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(model.device)
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=args.max_new_tokens,
            )
        latency_s = time.perf_counter() - started
        generated_ids = generated[:, inputs.input_ids.shape[1] :]
        raw = processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        parsed = _parse_object(raw)
        verdicts.append(
            {
                "window_index": expected_index,
                "start_s": float(window["start_s"]),
                "end_s": float(window["end_s"]),
                **parsed,
                "raw_output": raw,
                "latency_s": latency_s,
                "pair_path": str(image_path),
            }
        )
        print(
            f"COSMOS_WINDOW={expected_index} MATCH={parsed['match']} LATENCY_S={latency_s:.6f}",
            flush=True,
        )

    output = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "precision": "bfloat16",
        "decoding": {"do_sample": False, "max_new_tokens": args.max_new_tokens},
        "fixed_question": FIXED_QUESTION,
        "model_load_s": load_s,
        "verdicts": verdicts,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
