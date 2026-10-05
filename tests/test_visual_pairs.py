import json
from pathlib import Path

from tools.make_visual_pairs import build_ffmpeg_command, load_render_fps


def test_visual_pair_command_normalizes_both_inputs_to_same_height() -> None:
    command = build_ffmpeg_command("human.mp4", "robot.mp4", 0.5, 0.4, Path("pair.jpg"))

    filter_graph = command[command.index("-filter_complex") + 1]
    assert "[0:v]scale=-2:480" in filter_graph
    assert "[1:v]scale=-2:480" in filter_graph
    assert "scale=640:-2" not in filter_graph


def test_visual_pair_uses_recorded_render_fps(tmp_path: Path) -> None:
    metadata = tmp_path / "render_meta.json"
    metadata.write_text(json.dumps({"render_fps": 24.0}), encoding="utf-8")
    assert load_render_fps(metadata) == 24.0
