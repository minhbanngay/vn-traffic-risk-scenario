# Pilot INT-01 — kết quả CARLA ngày 20/10/2026

Batch: `int_01_pilot_guarded_v1`. [Manifest](../outputs/v2/batches/int_01_pilot_guarded_v1/manifest.json), [kiểm chứng tổng hợp](../outputs/v2/batches/int_01_pilot_guarded_v1/validation.json).

**10/10 cặp đạt evaluator; ba baseline đều đạt, độ lệch các mốc bằng 0 s.** Mọi cặp được chọn có prefix position/velocity error bằng 0, không collision, không thiếu RGB, không thay ngưỡng nghiệm thu phiên bản 1. Cả R và CF trong mỗi cặp dùng cùng frozen layout, camera, seed và chính sách ego.

## Ma trận đã chọn

Khoảng cách là vị trí xe máy phía sau ego lúc bắt đầu. Cột nguy hiểm là khoảng thời gian liên tục có headway dương <1 s khi lấn hành lang ego; cột giảm tốc đo trong 2 s sau trigger. CF của mọi dòng nhường ego, nhập phía sau với headway >=2 s và không kích hoạt hazard.

| Xe máy (km/h) | Sau ego (m) | Ảnh R / CF | Headway nguy hiểm (s) | Ego giảm (km/h) | Video và biểu đồ |
|---|---|---|---|---|---|
|36|6|198 / 329|0,85|12,19|[R–CF](../outputs/v2/INT-01/P-49174fef8ead/A000001/review.html)|
|36|7|204 / 334|0,80|12,20|[R–CF](../outputs/v2/INT-01/P-547f66b2e6b9/A000001/review.html)|
|36|8|209 / 339|0,80|12,21|[R–CF](../outputs/v2/INT-01/P-ac3584c9fba1/A000001/review.html)|
|36|9|215 / 344|0,80|12,22|[R–CF](../outputs/v2/INT-01/P-2a2c2e8c2510/A000001/review.html)|
|36|10|221 / 349|0,80|12,23|[R–CF](../outputs/v2/INT-01/P-f3a65875cba3/A000002/review.html)|
|38|6|187 / 323|0,70|12,11|[R–CF](../outputs/v2/INT-01/P-7675596103d7/A000001/review.html)|
|38|7|192 / 327|0,70|12,12|[R–CF](../outputs/v2/INT-01/P-0cd3308ba5f7/A000001/review.html)|
|38|8|196 / 328|0,75|12,18|[Baseline R–CF](../outputs/v2/INT-01/P-dd171995fc57/A000001/review.html)|
|38|9|202 / 334|0,70|12,19|[R–CF](../outputs/v2/INT-01/P-7b2338725f34/A000002/review.html)|
|38|10|207 / 339|0,70|12,21|[R–CF](../outputs/v2/INT-01/P-54c673d2eb3a/A000002/review.html)|

10 cặp có 5.377 ảnh và 20 video. Hai repeat bổ sung có 1.048 ảnh và 4 video, không được tính thành cặp mới. Tổng tập được chọn: 6.425 ảnh, 24 video, 12 pair attempts. Các attempt lỗi/gián đoạn nằm ngoài tập được chọn nhưng được giữ nguyên.

## Baseline và phiên bản

Baseline 38 km/h, sau ego 8 m: `P-dd171995fc57/A000001`, `A000002`, `A000003`. Mỗi lần có R 196 frame, CF 328 frame, đủ tail 4 s. Các mốc R intervention/merge_started/ego_response_triggered/merge_completed và CF intervention/merge_started/merge_completed có spread 0 s, nhỏ hơn giới hạn 0,15 s.

Town10HD_Opt/ClearNoon; ego Tesla Model 3 25 km/h; Yamaha YZF; seed 42; timestep/camera 0,05 s; JPEG 1280×720 quality 85; H=8, horizon step 0,5 s. Config revision 2 dùng vùng maneuver 80 m và route 130 m, được kiểm tra bằng diễn tập CF/tail trước thu. Tất cả mẫu được chọn dùng decision_lead_m=2,5; không cần chọn các timing hiệu chỉnh khác.

Python 3.12.15, CARLA 0.9.16 từ wheel đi kèm server, NumPy 1.26.4. Implementation fingerprint của mọi attempt được chọn: `a9d975f02ffd714db87a5ba14f59f1652bce884086bbbba4e242a87571a0921f`. Phiên bản dependencies, hash native CARLA và common config nằm trong từng `pair.json`; telemetry GPU nằm trong `server_<stage>.telemetry.jsonl`.

## Kiểm tra bổ sung và lịch sử lỗi

Audit bổ sung **passed=true**: giải mã đủ 24 MP4 / 6.425 frame, khớp số ảnh, mọi đoạn sau merge tiến đúng chiều route, không quay ngược. Headway CF nhỏ nhất khi cùng hành lang và đang/đã nhập làn: 3,133 s. Sai lệch ngang lớn nhất của xe máy sau completion khoảng 0,338 m. Telemetry của 12 attempts được chọn ghi nhận GPU tối đa 65°C, VRAM tối đa 5.936 MiB/6.144 MiB, không lần chạm guard. Kết quả đầy đủ trong [audit-final.json](../outputs/v2/batches/int_01_pilot_guarded_v1/audit-final.json). Trang review chứa video và đồ thị tốc độ, khoảng hở, headway, nhãn để tiếp tục rà soát trực quan.

Bộ test cuối: 76 passed. CLI evaluate batch trả exit code 0/passed=true. Kiểm tra resume giữ nguyên danh sách attempts được chọn và baseline repeats, không tạo attempt mới; nhánh thu dữ liệu được chặn trong phép kiểm tra này để phát hiện mọi yêu cầu khởi động thừa. Kết thúc không còn process CARLA hoặc batch.lock. Tổng lịch sử cohort có 15 attempts: 12 được chọn và ba lỗi/gián đoạn được giữ lại.

- `P-f3a65875cba3/A000001`: CF thiếu một ảnh do callback frame 241 đến sau timeout; giữ failed, chọn A000002 thu đủ ảnh. Không ghép bù hoặc sửa nhãn của attempt lỗi.
- `P-7b2338725f34/A000001`: planning chưa hoàn tất khi phiên cũ dừng; không còn runner sau lần mở máy tiếp theo, khóa được lưu lại và chọn A000002.
- `P-54c673d2eb3a/A000001`: cổng 2000 bận trước khi khởi động engine. Không dừng process khác; xác minh cổng trống rồi chạy A000002.

Chi tiết reboot cũ và giới hạn chẩn đoán nằm trong [runtime-incident](runtime-incident.md); không suy diễn rằng nguyên nhân phần cứng đã được xác định hay sửa xong. Không cập nhật driver hoặc power settings.

## Phạm vi bàn giao

Đây là pilot INT-01 và khuôn mẫu cho danh mục 20 tình huống. INT-02…INT-20 vẫn planned; chưa thêm weather augmentation, traffic ngẫu nhiên hoặc sensor mới. Legacy safe/risk/collision và dữ liệu INT_MOTO_001 không bị đổi thành R–CF hoặc ghi đè.
