# VN-Traffic Risk — CARLA Scenario Starter

Project thử nghiệm end-to-end cho một basic scenario:

> Ego chạy thẳng, motorcycle chạy ở lane kế bên rồi cut-in vào trước ego.

Một config có thể chạy thành ba variants:

- `safe`: motorcycle nhập lane sớm hơn ego;
- `risk`: motorcycle nhập lane sát trước ego, ego có phản ứng phanh;
- `collision`: hai xe được đồng bộ để đến merge point gần cùng thời điểm.

Project target CARLA `0.9.15–0.9.16`. Code không sao chép implementation từ RiskBench. RiskBench được dùng làm tham khảo về cách tách scenario-based collection và evaluation; project này tập trung vào scenario generation, recording và temporal risk labels.

## 1. Cấu trúc

```text
vn_traffic_risk_scenario/
├── configs/
│   └── scenarios/
│       └── motorcycle_cut_in.yaml
├── scripts/
│   ├── inspect_candidates.py
│   └── run_all_variants.py
├── src/vn_traffic_risk/
│   ├── actors.py
│   ├── carla_runtime.py
│   ├── cli.py
│   ├── config.py
│   ├── control.py
│   ├── math_utils.py
│   ├── models.py
│   ├── placement.py
│   ├── projection.py
│   ├── recorder.py
│   ├── risk.py
│   ├── scenario.py
│   └── sensors.py
└── tests/
```

## 2. Cài môi trường

Mở terminal tại thư mục project:

```bash
python -m venv .venv
```

Kích hoạt virtual environment theo hệ điều hành, sau đó:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev,video]"
```

CARLA Python API phải khớp với CARLA server của bạn. Kiểm tra:

```bash
python -c "import carla; print(carla.__file__)"
```

Nếu import lỗi, cài wheel đi kèm bản CARLA đang dùng hoặc thêm thư mục `PythonAPI/carla` vào `PYTHONPATH`.

## 3. Kiểm tra config trước khi mở CARLA

```bash
python -m vn_traffic_risk \
  --config configs/scenarios/motorcycle_cut_in.yaml \
  --variant risk \
  --dry-run
```

Lệnh này không kết nối server. Nó kiểm tra YAML và in config sau khi áp dụng variant profile.

## 4. Chạy CARLA server

Khởi động CARLA server trước. Project mặc định kết nối:

```text
host: 127.0.0.1
port: 2000
map: Town10HD_Opt
```

Nếu server của bạn dùng map name khác, sửa `carla.map` trong YAML.

## 5. Tìm vị trí cut-in trên map

Project tự tìm các đoạn:

- không nằm trong junction;
- tương đối thẳng;
- có hai driving lanes cùng chiều;
- đủ dài để spawn và hoàn thành maneuver.

Liệt kê các candidate:

```bash
python scripts/inspect_candidates.py \
  --config configs/scenarios/motorcycle_cut_in.yaml \
  --limit 30
```

Chọn một dòng phù hợp rồi sửa:

```yaml
placement:
  candidate_index: 0
```

Nếu candidate đầu nằm ở vị trí không đẹp, thử `1`, `2`, `3`... mà không cần sửa code.

## 6. Chạy một episode

```bash
python -m vn_traffic_risk \
  --config configs/scenarios/motorcycle_cut_in.yaml \
  --variant risk
```

Ba lựa chọn hợp lệ:

```text
safe
risk
collision
```

Chạy liên tiếp cả ba:

```bash
python scripts/run_all_variants.py \
  --config configs/scenarios/motorcycle_cut_in.yaml
```

## 7. Luồng điều khiển

```text
Map waypoint search
        ↓
Adjacent-lane pair
        ↓
Ego route + motorcycle route
        ↓
Smooth cut-in curve
        ↓
ETA synchronization
        ↓
Speed/heading controller
        ↓
CARLA VehicleControl
```

Ego giữ target speed. Motorcycle được điều chỉnh tốc độ theo:

```text
desired_actor_eta = ego_eta + target_time_offset_seconds
```

Giá trị mặc định:

```text
safe      -2.00 s
  risk      -1.25 s
collision  0.00 s
```

Các giá trị này là tham số khởi đầu. Kết quả thật còn phụ thuộc vehicle physics, map và controller, vì vậy phải kiểm tra output trước khi dùng làm ground truth chính thức.

Với variant `risk`, xe máy bắt đầu ở làn trái và sau ego 8 m, tăng tốc để
nhập sang phải vào làn ego với khoảng cách mục tiêu khoảng 7 m. Ego giảm tốc
từ 25 km/h về khoảng 12,5 km/h rồi tự tăng tốc trở lại. Episode kết thúc 3 giây
sau khi xe máy hoàn thành nhập làn để tránh actor chạy vòng quanh waypoint cuối.

Camera RGB dựa trên công thức góc nhìn thứ nhất của
`PythonAPI/examples/manual_control.py`, sau đó được lùi và hạ nhẹ để phần mũi
Tesla Model 3 xuất hiện ở phía dưới ảnh.

## 8. Output

```text
outputs/
└── INT_MOTO_001/
    └── INT_MOTO_001_V008/
        ├── safe/
        ├── risk/
        │   ├── episode.json
        │   ├── frames.jsonl
        │   ├── resolved_config.yaml
        │   └── rgb/
        └── collision/
```

Ảnh RGB được lưu dưới dạng JPEG chất lượng 85 theo mặc định để giảm dung lượng:

```yaml
recording:
  save_rgb: true
  image_format: jpeg
  jpeg_quality: 85
```

Đổi `image_format` về `png` nếu cần ảnh lossless. Có thể giảm thêm dung lượng bằng
cách giảm `image_width`, `image_height`, hoặc tăng `camera_tick_seconds` để ghi ít
frame hơn.

### Tạo video MP4

Sau khi episode chạy xong, ghép thư mục RGB thành video H.264:

```bash
python scripts/frames_to_video.py outputs/INT_MOTO_001/INT_MOTO_001_V008/risk
```

Video được lưu tại `risk/episode.mp4`. FPS được suy ra tự động từ
`recording.camera_tick_seconds` (mặc định 20 FPS). Có thể điều chỉnh chất lượng video:

```bash
python scripts/frames_to_video.py outputs/INT_MOTO_001/INT_MOTO_001_V008/risk --crf 28 --overwrite
```

CRF cao hơn tạo file nhỏ hơn nhưng giảm chất lượng; khoảng `23–28` phù hợp để xem
lại. Chỉ xóa thư mục `rgb/` sau khi đã kiểm tra video và nếu không còn cần các ảnh
riêng lẻ cho dataset.

Mỗi frame trong `frames.jsonl` có:

```text
frame_id, timestamp
ego state
risk actor state
2D bounding box
distance
ETA ego / actor
predicted closest approach
is_risk
interaction_type
future_risk_vector H=8
```

`episode.json` chứa:

```text
scenario_id
episode_id
variant
risk intervals
collision events
map/lane placement metadata
```

## 9. Labelling rule hiện tại

Một frame được xem là risk nếu có ít nhất một điều kiện:

1. collision sensor phát hiện sự kiện;
2. chênh lệch ETA tại merge point nhỏ hơn ngưỡng;
3. predicted closest distance nhỏ hơn ngưỡng;
4. current distance nhỏ hơn ngưỡng trong lúc maneuver đang active.

Risk Tube được sinh sau khi episode kết thúc:

```text
z_h = risk tại frame hiện tại + h × horizon_stride
```

Với config mặc định:

```text
H = 8
horizon step = 0.5 s
simulation step = 0.05 s
```

Mỗi phần tử Risk Tube cách nhau 10 simulation frames.

## 10. Chạy tests

```bash
pytest -q
```

Tests không yêu cầu CARLA server. Chúng kiểm tra:

- variant config;
- lane-change interpolation;
- closest-approach calculation;
- ETA-based risk label;
- Risk Tube stride;
- risk interval extraction.

## 11. Phạm vi phiên bản đầu

Đã có:

- deterministic synchronous stepping;
- automatic adjacent-lane placement;
- ego và risk-actor routes;
- safe/risk/collision timing profiles;
- RGB camera;
- collision sensor;
- actor states;
- projected 2D box;
- JSONL recording;
- Risk Tube `H=8`;
- pure-Python tests.

Chưa đưa vào bản đầu:

- background traffic;
- weather/context batch augmentation;
- pedestrian controller;
- depth/semantic/BEV;
- nhiều risk actors trong một episode;
- calibration stream và dataset split generator.

Nên chạy ổn scenario này trước. Sau khi kiểm tra trajectory và labels, mới mở rộng sang crossing, overtaking, obstacle và occlusion.
