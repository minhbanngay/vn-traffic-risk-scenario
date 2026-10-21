from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..evaluation.risk import future_vectors
from ..recorder import EpisodeRecorder as LegacyImageWriter


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix+".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class EpisodeRecorder:
    def __init__(self, directory: Path, config: dict, layout: dict, identity: dict):
        self.output_dir, self.data, self.identity = directory, config, identity
        directory.mkdir(parents=True, exist_ok=False)
        self.rgb_dir = directory/"rgb"
        self.rgb_dir.mkdir()
        with (directory/"resolved_config.yaml").open("w", encoding="utf-8") as stream:
            yaml.safe_dump(config, stream, sort_keys=False)
        write_json(directory/"layout.json", layout)
        write_json(directory/"episode.json", {**identity, "status": "running", "frame_count": 0})
        self.raw = (directory/"frames.raw.jsonl").open("x", encoding="utf-8")
        self.event_stream = (directory/"events.jsonl").open("x", encoding="utf-8")
        self.frames, self.events = [], []

    def save_rgb(self, image) -> str:
        # Reuse the existing PNG/JPEG encoder without invoking its legacy path resolver.
        writer = object.__new__(LegacyImageWriter)
        writer.config = type("ImageConfig", (), {"data": self.data})()
        writer.output_dir = self.output_dir
        return writer.save_rgb(image)

    def event(self, value: dict) -> None:
        self.events.append(value)
        self.event_stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False)+"\n")
        self.event_stream.flush()

    def append(self, row: dict) -> None:
        self.frames.append(row)
        self.raw.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
        self.raw.flush()

    def finalize(self, collision_events: list[dict], status="complete", error=None):
        # Sensor callbacks can arrive after the frame was originally recorded.
        first = self.frames[0]["frame_id"] if self.frames else 0
        collisions = [e for e in collision_events if e["frame"] >= first]
        collision_frames = {e["frame"] for e in collisions}
        for row in self.frames:
            now = row["frame_id"] in collision_frames
            row["risk"]["collision_now"] = now
            row["risk"]["collision_occurred"] = any(f <= row["frame_id"] for f in collision_frames)
            if now:
                row["risk"]["is_risk"] = True
                if "collision_sensor" not in row["risk"]["reasons"]:
                    row["risk"]["reasons"].append("collision_sensor")
        cfg = self.data["risk_labelling"]
        future_vectors(self.frames, cfg["horizon"], cfg["horizon_step_seconds"], self.data["carla"]["fixed_delta_seconds"])
        final_path = self.output_dir/"frames.jsonl"
        with final_path.with_suffix(".jsonl.tmp").open("w", encoding="utf-8") as stream:
            for row in self.frames:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
        final_path.with_suffix(".jsonl.tmp").replace(final_path)
        missing = sum(not r["rgb_file"] for r in self.frames)
        if status == "complete" and missing:
            status, error = "incomplete", f"{missing} missing RGB frames"
        for event in collisions:
            self.event({"event": "collision_sensor", **event})
        summary = {**self.identity, "status": status, "error": error, "frame_count": len(self.frames),
                   "missing_rgb_frames": missing, "collision_events": collisions,
                   "maneuver_events": [e for e in self.events if e["event"] in {
                       "intervention", "merge_started", "merge_completed", "ego_response_triggered",
                       "maneuver_started", "maneuver_completed", "squeeze_reached", "separation_started",
                       "braking_started", "braking_target_reached", "recovery_started"}]}
        write_json(self.output_dir/"episode.json", summary)
        return summary

    def close(self):
        self.raw.close()
        self.event_stream.close()
