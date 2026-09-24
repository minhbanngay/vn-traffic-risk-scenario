import json
from pathlib import Path

import yaml
from PIL import Image

from vn_traffic_risk.video import find_frames, infer_fps


def test_find_frames_accepts_episode_directory_and_sorts_frames(tmp_path: Path) -> None:
    rgb_dir = tmp_path / "rgb"
    rgb_dir.mkdir()
    Image.new("RGB", (2, 2)).save(rgb_dir / "00000002.jpg")
    Image.new("RGB", (2, 2)).save(rgb_dir / "00000001.png")

    resolved_rgb_dir, frames = find_frames(tmp_path)

    assert resolved_rgb_dir == rgb_dir.resolve()
    assert [path.name for path in frames] == ["00000001.png", "00000002.jpg"]


def test_infer_fps_from_resolved_config(tmp_path: Path) -> None:
    rgb_dir = tmp_path / "rgb"
    rgb_dir.mkdir()
    with (tmp_path / "resolved_config.yaml").open("w", encoding="utf-8") as stream:
        yaml.safe_dump(
            {
                "carla": {"fixed_delta_seconds": 0.05},
                "recording": {"camera_tick_seconds": 0.1},
            },
            stream,
        )

    assert infer_fps(rgb_dir, None) == 10.0
    assert infer_fps(rgb_dir, 10.0) == 10.0


def test_find_frames_uses_current_frames_jsonl_when_formats_are_mixed(
    tmp_path: Path,
) -> None:
    rgb_dir = tmp_path / "rgb"
    rgb_dir.mkdir()
    Image.new("RGB", (2, 2)).save(rgb_dir / "00000001.png")
    Image.new("RGB", (2, 2)).save(rgb_dir / "00000001.jpg")
    Image.new("RGB", (2, 2)).save(rgb_dir / "stale.png")
    with (tmp_path / "frames.jsonl").open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"rgb_file": "rgb/00000001.jpg"}) + "\n")

    _, frames = find_frames(tmp_path)

    assert [path.name for path in frames] == ["00000001.jpg"]
