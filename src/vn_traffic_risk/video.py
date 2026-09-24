from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image


def find_frames(episode_or_rgb_dir: str | Path) -> tuple[Path, list[Path]]:
    source = Path(episode_or_rgb_dir).expanduser().resolve()
    rgb_dir = source / "rgb" if (source / "rgb").is_dir() else source
    if not rgb_dir.is_dir():
        raise ValueError(f"RGB directory does not exist: {rgb_dir}")

    frames_file = rgb_dir.parent / "frames.jsonl"
    if frames_file.is_file():
        recorded_frames: list[Path] = []
        with frames_file.open("r", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                rgb_file = record.get("rgb_file")
                if rgb_file:
                    frame_path = rgb_dir.parent / str(rgb_file)
                    if frame_path.is_file():
                        recorded_frames.append(frame_path)
        if recorded_frames:
            return rgb_dir, recorded_frames

    frames = sorted(
        path
        for path in rgb_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    if not frames:
        raise ValueError(f"No PNG/JPEG frames found in: {rgb_dir}")
    return rgb_dir, frames


def infer_fps(rgb_dir: Path, requested_fps: float | None) -> float:
    if requested_fps is not None:
        if requested_fps <= 0:
            raise ValueError("FPS must be positive")
        return requested_fps

    config_path = rgb_dir.parent / "resolved_config.yaml"
    if config_path.is_file():
        with config_path.open("r", encoding="utf-8") as stream:
            config: Any = yaml.safe_load(stream)
        frame_interval = float(
            config.get("recording", {}).get(
                "camera_tick_seconds",
                config["carla"]["fixed_delta_seconds"],
            )
        )
        if frame_interval > 0:
            return 1.0 / frame_interval
    return 20.0


def create_video(
    episode_or_rgb_dir: str | Path,
    output: str | Path | None = None,
    fps: float | None = None,
    crf: int = 23,
    overwrite: bool = False,
) -> Path:
    if not 0 <= crf <= 51:
        raise ValueError("CRF must be between 0 and 51")

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            'Video support is not installed. Run: python -m pip install -e ".[video]"'
        ) from exc

    rgb_dir, frames = find_frames(episode_or_rgb_dir)
    output_path = (
        Path(output).expanduser().resolve()
        if output is not None
        else rgb_dir.parent / "episode.mp4"
    )
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}. Use --overwrite to replace it."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    video_fps = infer_fps(rgb_dir, fps)

    with Image.open(frames[0]) as first:
        width, height = first.size

    writer = imageio_ffmpeg.write_frames(
        str(output_path),
        (width, height),
        fps=video_fps,
        codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        quality=None,
        macro_block_size=2,
        output_params=["-crf", str(crf), "-movflags", "+faststart"],
        ffmpeg_log_level="warning",
    )
    writer.send(None)
    try:
        for index, frame_path in enumerate(frames, start=1):
            with Image.open(frame_path) as image:
                if image.size != (width, height):
                    raise ValueError(
                        f"Frame size mismatch: {frame_path} is {image.size}, "
                        f"expected {(width, height)}"
                    )
                writer.send(np.asarray(image.convert("RGB"), dtype=np.uint8))
            if index % 100 == 0 or index == len(frames):
                print(f"Encoded {index}/{len(frames)} frames")
    finally:
        writer.close()

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an MP4 video from a recorded episode's RGB frames."
    )
    parser.add_argument(
        "episode_or_rgb_dir",
        help="Episode directory (containing rgb/) or the rgb directory itself",
    )
    parser.add_argument("--output", help="Output MP4 path (default: episode.mp4)")
    parser.add_argument("--fps", type=float, help="Override inferred simulation FPS")
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="H.264 quality: 0 is lossless, 23 is default, 51 is smallest",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        output_path = create_video(
            args.episode_or_rgb_dir,
            output=args.output,
            fps=args.fps,
            crf=args.crf,
            overwrite=args.overwrite,
        )
    except (FileExistsError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Video saved to: {output_path} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
