from pathlib import Path

import numpy as np
from PIL import Image

from vn_traffic_risk.config import ResolvedConfig
from vn_traffic_risk.recorder import EpisodeRecorder


class FakeCarlaImage:
    frame = 42
    width = 8
    height = 4

    def __init__(self) -> None:
        bgra = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        bgra[:, :, 0] = 10
        bgra[:, :, 1] = 20
        bgra[:, :, 2] = 200
        bgra[:, :, 3] = 255
        self.raw_data = bgra.tobytes()


def test_save_rgb_as_compressed_jpeg(tmp_path: Path) -> None:
    data = {
        "scenario": {
            "scenario_id": "scenario",
            "episode_id": "episode",
            "variant": "risk",
        },
        "recording": {
            "output_root": str(tmp_path),
            "save_rgb": True,
            "image_format": "jpeg",
            "jpeg_quality": 85,
        },
    }
    config = ResolvedConfig(data, tmp_path / "config.yaml")
    recorder = EpisodeRecorder(config, {})

    relative_path = recorder.save_rgb(FakeCarlaImage())

    assert relative_path == "rgb/00000042.jpg"
    saved_path = recorder.output_dir / relative_path
    assert saved_path.is_file()
    with Image.open(saved_path) as saved:
        assert saved.format == "JPEG"
        assert saved.size == (8, 4)
