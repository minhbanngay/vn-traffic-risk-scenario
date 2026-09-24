from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from .config import ResolvedConfig
from .models import FrameRecord
from .risk import build_future_risk_vectors, risk_intervals


class EpisodeRecorder:
    def __init__(self, config: ResolvedConfig, layout_description: dict[str, Any]) -> None:
        self.config = config
        self.output_dir = config.output_directory
        self.rgb_dir = self.output_dir / "rgb"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if bool(config.data["recording"]["save_rgb"]):
            self.rgb_dir.mkdir(parents=True, exist_ok=True)
        self.frames: list[FrameRecord] = []
        self.layout_description = layout_description

    def save_rgb(self, image: Any) -> str:
        recording = self.config.data["recording"]
        image_format = str(recording.get("image_format", "png")).lower()
        extension = "jpg" if image_format in {"jpg", "jpeg"} else "png"
        relative = Path("rgb") / f"{int(image.frame):08d}.{extension}"
        destination = self.output_dir / relative

        if extension == "png":
            image.save_to_disk(str(destination))
        else:
            bgra = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(
                (int(image.height), int(image.width), 4)
            )
            rgb = np.ascontiguousarray(bgra[:, :, :3][:, :, ::-1])
            Image.fromarray(rgb).save(
                destination,
                format="JPEG",
                quality=int(recording.get("jpeg_quality", 85)),
                optimize=True,
            )
        return relative.as_posix()

    def append(self, frame: FrameRecord) -> None:
        self.frames.append(frame)

    def finalize(self, collision_events: list[dict[str, Any]]) -> dict[str, Any]:
        risk_mask = [frame.risk.is_risk for frame in self.frames]
        risk_cfg = self.config.data["risk_labelling"]
        vectors = build_future_risk_vectors(
            risk_mask,
            int(risk_cfg["horizon"]),
            float(risk_cfg["horizon_step_seconds"]),
            self.config.fixed_delta_seconds,
        )
        for frame, vector in zip(self.frames, vectors):
            frame.future_risk_vector = vector

        with (self.output_dir / "frames.jsonl").open("w", encoding="utf-8") as stream:
            for frame in self.frames:
                stream.write(json.dumps(frame.as_dict(), ensure_ascii=False) + "\n")

        summary = {
            "scenario_id": self.config.scenario_id,
            "episode_id": self.config.episode_id,
            "variant": self.config.variant,
            "interaction_type": self.config.data["scenario"]["interaction_type"],
            "frame_count": len(self.frames),
            "risk_intervals": risk_intervals(
                [frame.frame_id for frame in self.frames],
                risk_mask,
            ),
            "collision_events": collision_events,
            "layout": self.layout_description,
        }
        with (self.output_dir / "episode.json").open("w", encoding="utf-8") as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2)
        with (self.output_dir / "resolved_config.yaml").open("w", encoding="utf-8") as stream:
            yaml.safe_dump(self.config.data, stream, sort_keys=False, allow_unicode=True)
        return summary
