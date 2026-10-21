# Trạng thái triển khai INT-01

Cập nhật 21/10/2026: đã triển khai thêm INT-03/05/08, có 126 test hồi quy/unit/integration qua. INT-03 có một cặp mẫu đạt; INT-05 và INT-08 chưa có cặp đạt, còn hiệu chỉnh/xác nhận. Chi tiết nằm trong [báo cáo đợt 2](wave-2.md); không coi trạng thái implemented/sample_validated là pilot_validated. Phần dưới ghi mốc INT-01 và lịch sử trước khi mở rộng.

**Hiện tại: pilot INT-01 hoàn tất kiểm chứng tự động trên CARLA.** Batch `int_01_pilot_guarded_v1` đạt 10/10 cặp, cả ba baseline đạt với event spread 0 s; audit giải mã đủ 24 video / 6.425 frame, không thiếu RGB/collision. CLI evaluate và kiểm tra resume đều qua, không còn engine hoặc khóa batch. [Báo cáo đầy đủ và video](pilot-INT-01.md). Các đoạn bên dưới giữ lịch sử triển khai và những cohort không đạt, không phải trạng thái hiện tại.

Đã có catalog đủ 20 dòng Excel, schema 2, cấu hình chung/can thiệp, planner đóng băng layout, R–CF cut-in/nhường, detector footprint, durable recording, Risk Tube validity, video/review và evaluator. CLI legacy được giữ lại. Các scenario INT-02…INT-20 vẫn là planned.

Bộ kiểm thử hiện tại: **76 passed** trên môi trường `.venv-carla312` (Python 3.12.15, CARLA 0.9.16 từ wheel đi kèm server, NumPy 1.26.4). Bao gồm config, geometry, state machine, ACK command batches, frozen decision, preflight CF/tail, lifecycle, sensor thiếu/trùng, collision đến muộn, dữ liệu ghi dở, pairing, resume, checkpoint trước khi khởi động engine, repeat context, GPU telemetry/guard, giới hạn số attempt, giải mã video và kiểm tra tiến độ route. Fixture acceptance dùng trạng thái/ảnh tổng hợp và không được tính là dữ liệu CARLA thực.

Các thử nghiệm thực tế và lỗi đều nằm trong outputs/v2; không tính attempt failed/incomplete/rejected thành dữ liệu đạt.

Một cặp mẫu thực tế đã đạt: `outputs/v2/INT-01/P-d6e9f6316bef/A000004`. R 218 frame, CF 352 frame, không thiếu RGB và không collision; prefix position/velocity error bằng 0. R có 0,75 s headway nguy hiểm, ego giảm khoảng 12,19 km/h trong cửa sổ nghiệm thu. CF nhập phía sau an toàn. `review.html` chứa hai video và biểu đồ.

Cohort runtime mới `int_01_pilot_cp312_fresh_engines_v2` đã có cặp revision 2 đầu tiên đạt: `outputs/v2/INT-01/P-ce3ae15f7a5e/A000001` (36 km/h, sau ego 6 m). R 198 frame, CF 329 frame; không thiếu RGB/collision; sai lệch prefix bằng 0; headway nguy hiểm liên tục 0,85 s, ego giảm 12,19 km/h. Xem [review](../outputs/v2/INT-01/P-ce3ae15f7a5e/A000001/review.html) và [validation](../outputs/v2/INT-01/P-ce3ae15f7a5e/A000001/validation.json). Đây là một cặp đã đạt, chưa phải xác nhận cả batch 10 cặp.

**Lần bàn giao trước: chưa hoàn tất nghiệm thu dữ liệu.** Máy khởi động lại bất thường khi đang bắt đầu nhánh R của cặp thứ hai. Batch cũ được đánh dấu interrupted, 1/10 cặp đạt, baseline chưa chạy. Bằng chứng và hướng phục hồi nằm trong [runtime-incident](runtime-incident.md). Chưa thể xác định nguyên nhân reboot từ Kernel-Power 41/EventLog 6008.

Ngày 20/10, người dùng yêu cầu tiếp tục. Cohort `int_01_pilot_guarded_v1` có giới hạn render và telemetry GPU riêng cho mỗi engine. Cặp smoke test `P-49174fef8ead/A000001` đã đạt (R 198/CF 329 frame, missing RGB=0, prefix error=0), GPU tối đa 58°C, không chạm guard. Sau khi resume các phần còn lại, validation tổng hợp và ba baseline đều đạt; báo cáo cuối ở đầu tài liệu này.

Mốc 10 cặp và ba baseline chỉ được công bố hoàn tất nếu batch validation passed=true. Các batch thử trước đó chưa đạt: có lỗi RPC/native và một cặp lệch prefix 0,137 m / 0,233 m/s, nên đã bị từ chối theo ngưỡng gốc.

Windows Application Error log đã ghi lỗi python.exe trong libcarla.cp310-win_amd64.pyd với exception 0xc0000005, và các abort ucrtbase.dll 0xc0000409. Không suy ra mọi lỗi đều do cùng nguyên nhân. Runtime bổ sung SDK worker isolation, owned-server scope, world readiness và Windows worker shutdown sau cleanup/flush để thu thập và xử lý lỗi minh bạch.

Đối chiếu SDK: bản phân phối server có wheel cp312, nên đã tạo môi trường cục bộ riêng; không thay môi trường cp310 cũ. Cohort `int_01_pilot_cp312_batched_v1` vẫn lỗi timeout lúc CF đọc settings sau reload (R đã thu 218 frame), cho thấy chưa thể quy toàn bộ lỗi về phiên bản Python/SDK. Cohort `int_01_pilot_cp312_fresh_engines_v1` lỗi load map trước khi thu. Các manifest/log được giữ nguyên. Runtime mới dùng engine riêng cho từng worker, bỏ load map trùng và cho phép RPC nạp/reset world tối đa 120 s.

Lệnh nghiệm thu/tiếp tục: `python -m vn_traffic_risk run-batch --config configs/batches/int_01_pilot_managed.yaml`. Batch ID trong YAML phân biệt những cohort implementation khác nhau; các cohort cũ được giữ nguyên.
