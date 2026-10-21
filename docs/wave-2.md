# Đợt 2 — INT-03, INT-05, INT-08

Ngày triển khai: 21/10/2026. Ba scenario đã có implementation, cấu hình, batch nhỏ, đặc tả và evaluator riêng. Trạng thái ban đầu: **implemented_pending_validation**; không đồng nghĩa có dữ liệu CARLA đạt.

| ID | Đặc tả | CF | Chỉ số nghiệm thu chính |
|---|---|---|---|
|INT-03|[Ép ngang](scenarios/group_a/INT-03.md)|Giữ khoảng cách ngang|Khoảng hở thân xe ngang khi chồng khoảng dọc|
|INT-05|[Vượt và nhập lại](scenarios/group_a/INT-05.md)|Chờ đủ khoảng hở phía trước rồi nhập|Headway phía trước khi overlap|
|INT-08|[Phanh xe dẫn đầu](scenarios/group_b/INT-08.md)|Giảm tốc sớm, từ từ|TTC, gia tốc dọc và thời điểm phanh|

Module dùng chung `scenarios/straight_road.py` sở hữu tìm site/rehearsal vật lý, kiểm tra zone/route và tail. Các module scenario chỉ sở hữu state machine. Registry khai báo mode can thiệp và các trường matrix/calibration cho từng ID. `evaluation/scenario_checks.py` tách nghiệm thu đặc thù khỏi invariant ảnh, nhãn và đối chứng trong validation.py.

Các metric bổ sung được bật rõ trong risk_labelling từng cấu hình; cấu hình INT-01 không đổi nên evaluator vẫn tính lại nhãn cũ theo quy tắc cũ. Không sửa dữ liệu/manifest INT-01. Thay Python implementation làm fingerprint mới: không resume thu thêm vào cohort INT-01 cũ; vẫn đọc/evaluate dữ liệu cũ được.

## Quy trình chạy

Activate môi trường `.venv-carla312` như README; để cổng 2000 trống. Managed engine vẫn Low/offscreen, cap 20 FPS, telemetry/guard GPU như INT-01, không sửa thiết lập máy.

```powershell
python -m vn_traffic_risk validate --config configs/scenarios/group_a/INT-03.yaml
python -m vn_traffic_risk validate --config configs/scenarios/group_a/INT-05.yaml
python -m vn_traffic_risk validate --config configs/scenarios/group_b/INT-08.yaml
python -m vn_traffic_risk run-pair --config configs/scenarios/group_a/INT-03.yaml
python -m vn_traffic_risk run-pair --config configs/scenarios/group_a/INT-05.yaml
python -m vn_traffic_risk run-pair --config configs/scenarios/group_b/INT-08.yaml
python -m vn_traffic_risk run-batch --config configs/batches/int_03_pilot_managed.yaml --dry-run
python -m vn_traffic_risk run-batch --config configs/batches/int_03_pilot_managed.yaml --max-new-attempts 1
```

Đổi `int_03` thành `int_05` hoặc `int_08` cho batch tương ứng. Mỗi batch ba pair tham số và hai repeat baseline bổ sung (tổng năm pair attempts nếu không có retry). Chỉ chạy batch đầy đủ sau khi một pair mẫu được xem video/đồ thị và đạt evaluator. Output theo `outputs/v2/<INT-ID>/<pair_id>/<attempt_id>/`, gồm review.html, R/CF, telemetry và validation. Không ghi đè attempt bị lỗi, không nới ngưỡng ngầm để đạt.

## Trạng thái nghiệm thu

126/126 test qua (28,14 s), gồm 76 test tại mốc INT-01 và 50 test mới cho config, state machine, hình học/nhãn, rehearsal/cleanup/brake limits, acceptance/ảnh/metric bị sửa, biểu đồ, completion ổn định, budget áp dụng cả baseline repeats, gain actor không ảnh hưởng ego và spawn cùng làn của INT-08. Fixture acceptance là dữ liệu tổng hợp trong thư mục tạm pytest, không phải output CARLA.

| ID | Pair mẫu CARLA | Kết quả |
|---|---|---|
|INT-03|[P-1d4f5231dfef/A000001](../outputs/v2/INT-03/P-1d4f5231dfef/A000001/review.html)|Đạt tự động: R 213/CF 221 frame, 0 thiếu RGB/collision, prefix 0 m/0 m/s. R khoảng hở ngang nguy hiểm 1,50 s, nhỏ nhất 0,2171 m; ego giảm 12,09 km/h. CF khoảng hở nhỏ nhất 1,9430 m.|
|INT-05|Revision 1/2 bị từ chối hoặc lỗi; revision 3 chờ thử lại|Chưa đạt; chi tiết ở đặc tả INT-05|
|INT-08|[P-b929b3b8e0c8/A000001](../outputs/v2/INT-08/P-b929b3b8e0c8/A000001/review.html)|Bị từ chối: R đạt, CF chưa giảm tốc nhẹ đúng tiêu chí; revision 2 chờ hiệu chỉnh/chạy lại|

Giới hạn hình ảnh INT-03: ở frame R khoảng hở nhỏ nhất (`00000201.jpg`, step 81), xe máy chếch sau ego và không hiện trong camera nhìn trước. Đã kiểm tra ảnh thật; không dùng ảnh tổng hợp thay thế. Metric footprint/trạng thái vẫn cho thấy chồng khoảng dọc và khoảng hở ngang dương. Mẫu này đạt tiêu chí động học tự động nhưng cần cân nhắc yêu cầu visibility của tập huấn luyện trước khi mở batch; chưa bổ sung camera hoặc thay ego/context giữa hai nhánh.

Chưa chạy batch ba pair + hai baseline repeat cho các ID mới; `sample_validated` chỉ xác nhận một cặp mẫu, không phải `pilot_validated`. Không tạo dữ liệu mô phỏng giả thay cho dữ liệu thu thật. INT-02/04/06/07 và INT-09…20 vẫn planned; chưa bổ sung supporting actors, pedestrian hay junction controller trong đợt này.

Lịch sử INT-05:

- `P-e82e1f52312e/A000001`: R 173/CF 229 frame, không thiếu RGB/collision, prefix bằng 0; R headway nguy hiểm 0,40 s, CF headway nhập nhỏ nhất 2,995 s. Cả hai bị từ chối vì lệch làn sau completion >0,35 m (overshoot khoảng 0,43 m).
- `P-aaef1ad578a3/A000001`: R 177 frame, headway nguy hiểm 0,55 s, vẫn bị từ chối do overshoot khoảng 0,351 m. CF mất engine ở `reload_world(False)`, timeout 120 s trước thu ảnh. Không có `health_guard_stop` trong telemetry, chưa xác định vì sao engine thoát; không quy lỗi cho GPU/driver/nguồn khi chưa có bằng chứng. Chỉ dừng worker CF PID 25840 sau khi xác minh parent/payload và engine đã gone; giữ log exception và mọi output. Đây là attempt failed, không tính là cặp đạt.
- Revision 3 bổ sung settling và điều kiện hướng/vận tốc ngang, chừa khoảng đường ổn định; cần pair CARLA mới trước khi mở batch. Không sửa các attempt cũ hoặc ngưỡng evaluator.

Kiểm tra hồi quy dữ liệu: 10 pair chọn và 2 repeat baseline INT-01 đều vẫn đạt khi gọi `evaluate_pair(save=False)` bằng evaluator mở rộng; không ghi đè validation cũ. Cặp INT-03 có `audit-sample-v1.json` đạt, giải mã đủ 434 frame của hai video và tail đi tiến.

INT-08 revision 1: R 272/CF 201 frame, không thiếu RGB/collision, prefix bằng 0. R đạt (TTC nguy hiểm 0,25 s, ego giảm 12,158 km/h). CF bị từ chối do gia tốc giảm đỉnh 4,839 m/s² >1,5 m/s²; dao động đã xuất hiện trước intervention, không kết luận nguyên nhân chỉ từ ramp tốc độ. Xem đặc tả INT-08 để biết chi tiết frame/control và hướng hiệu chỉnh. Revision 2 cho phép cấu hình gain riêng actor, giới hạn phanh cả recovery và thêm thông tin lệnh gear; không khẳng định đã giải quyết dao động khi chưa chạy CARLA lại.

Đợt chạy thử này kết thúc ở mức một cặp mẫu đạt INT-03; INT-05 revision 3 và INT-08 revision 2 còn cần CARLA xác nhận. Không chạy thêm engine/batch trong đợt bàn giao này. Các output bị từ chối/lỗi được giữ để đối chiếu, không tính vào dataset đạt.

Audit INT-08 giải mã đủ R 272/CF 201 frame và tail đi tiến, nhưng `audit-sample-v1.json` vẫn passed=false vì CF không đạt tiêu chí gia tốc; video đủ không đồng nghĩa tình huống đạt. Kiểm tra cuối: không còn CARLA engine hay Python runner/worker vn_traffic_risk. Hai khóa batch INT-01 cũ (`int_01_pilot`, `int_01_pilot_managed`, tạo trước đợt này) vẫn giữ nguyên; không có runner tương ứng, không tự xóa lịch sử cũ. Batch nghiệm thu `int_01_pilot_guarded_v1` không bị thay đổi.

Audit từng cặp (không sửa ảnh/nhãn, output audit phải là file mới):

```powershell
python scripts/audit_pilot.py outputs/v2/INT-03/P-1d4f5231dfef/A000001 --output outputs/v2/INT-03/P-1d4f5231dfef/A000001/audit-check-2.json
```
