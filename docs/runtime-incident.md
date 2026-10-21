# Gián đoạn nghiệm thu CARLA

## Kết quả giữ được

Batch `int_01_pilot_cp312_fresh_engines_v2` dừng ở **1/10 cặp đạt**, chưa chạy ba baseline. [Báo cáo batch](../outputs/v2/batches/int_01_pilot_cp312_fresh_engines_v2/validation.json) có `passed=false`, trạng thái interrupted.

- Cặp đạt: `P-ce3ae15f7a5e/A000001`, 36 km/h, sau ego 6 m. [Validation](../outputs/v2/INT-01/P-ce3ae15f7a5e/A000001/validation.json), [video và biểu đồ](../outputs/v2/INT-01/P-ce3ae15f7a5e/A000001/review.html).
- Cặp gián đoạn: `P-383786a12289/A000001`, 36 km/h, sau ego 7 m. Planner đã hoàn tất; R dừng trong startup/warm-up, chưa có frame thu chính. Đã đánh dấu incomplete, không tính đạt.
- Các lần thử cũ, dữ liệu legacy, RGB, video và log không bị xóa. Khóa cũ được giữ dưới tên `batch.lock.recovered-after-reboot` sau khi xác minh không còn process Python/CARLA.

## Bằng chứng hệ thống

Windows báo thời điểm boot mới `2026-10-19T16:55:34.500Z`, tương ứng 23:55:34 ngày 19/10 tại Asia/Saigon.

| Provider / event | UTC | Ý nghĩa |
|---|---|---|
| Microsoft-Windows-Kernel-Power / 41 | 2026-10-19T16:55:42.431Z | Khởi động lại mà chưa shutdown sạch |
| EventLog / 6008 | 2026-10-19T16:55:54.748Z | Lần shutdown trước, 23:54:01 ngày 19/10, là bất thường |

Các event này xác nhận reboot bất thường, **không xác định nguyên nhân**. Chưa đủ bằng chứng để kết luận do CARLA, driver GPU, nguồn điện, nhiệt độ hay thành phần khác. Lỗi RPC/native từ các thử nghiệm trước cũng không tự chứng minh nguyên nhân reboot.

## Phục hồi phần mềm và điều kiện chạy tiếp

Sau reboot chỉ thực hiện kiểm tra nhẹ, không khởi động CARLA. Bộ test cuối có 64 passed. Batch checkpoint đã được bổ sung để lưu attempt ngay khi cấp đường dẫn, trước mọi engine; kiểm thử xác nhận một lần ngắt process vẫn để lại tham chiếu attempt trong manifest.

Source fingerprint thay đổi bởi bản sửa checkpoint; cohort cũ được giữ nguyên. `configs/batches/int_01_pilot_managed.yaml` dùng batch ID mới `int_01_pilot_checkpointed_v1` cho lần chạy sau, chưa chạy và chưa có dữ liệu nghiệm thu. Không gộp cặp từ implementation/runtime khác thành ba baseline.

Trước khi tiếp tục tải mô phỏng cần người dùng quyết định việc kiểm tra ổn định máy và cho chạy lại. Sau đó: một cặp smoke test → xem video/metrics → batch 10 cặp → ba baseline → kiểm chứng tổng hợp. Không thay ngưỡng nghiệm thu để bù cho lỗi runtime.

## Tiếp tục ngày 20/10/2026

Người dùng yêu cầu tiếp tục. Kiểm tra mở rộng Event 41: BugcheckCode=0, PowerButtonTimestamp=0, LongPowerButtonPressDetected=false, WHEABootErrorCount=0. Không tìm thấy crash dump hoặc lỗi WHEA/bugcheck trong cửa sổ sự cố đã kiểm tra. Điều này vẫn không chứng minh nguyên nhân reboot; xem [hướng dẫn Event 41 của Microsoft](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/event-id-41-restart).

Trước khi thử lại: RTX 3050 Laptop 6 GB khoảng 44°C khi rảnh, pin 99%, RAM trống khoảng 7,4 GB và ổ D còn khoảng 58 GB. Đây là số đo tại thời điểm kiểm tra, không phải chứng nhận ổn định dưới tải.

Runtime mới giới hạn render bằng `-ExecCmds=t.MaxFPS 20`, giữ nguyên timestep/camera 0,05 s và thông số ảnh. Các console command theo [tài liệu Epic](https://dev.epicgames.com/documentation/unreal-engine/console-variables-cplusplus-in-unreal-engine). Mỗi engine có `server_<stage>.telemetry.jsonl`, đọc GPU qua nvidia-smi mỗi 5 s. Ngưỡng thận trọng của dự án: nhiệt độ GPU >=82°C, VRAM >=97%, hoặc ba lần probe liên tiếp lỗi sẽ dừng đúng engine do runner tạo. Probe đầu không có dữ liệu thì không khởi động engine. Không đổi driver, nguồn, xung hoặc giới hạn điện phần cứng. Giám sát này không bảo đảm ngăn được mọi lỗi reboot.

74 test tự động đã qua. Cohort mới `int_01_pilot_guarded_v1` bắt đầu bằng `run-batch --config configs/batches/int_01_pilot_managed.yaml --max-new-attempts 1`. Đây là dừng sạch theo ngân sách một attempt, vẫn dùng cùng manifest khi resume; `passed=false/status=partial` sau smoke test không có nghĩa toàn bộ batch đã đạt. Nghiệm thu vật lý/nhãn giữ nguyên các ngưỡng phiên bản 1.

## Kết quả sau phục hồi

Pilot đã hoàn tất: 10/10 cặp, ba baseline cùng đạt với event spread 0 s; audit đủ 24 video / 6.425 ảnh. Bộ test cuối có 76 passed, CLI evaluate exit code 0, resume không tạo attempt mới. [Báo cáo và video](pilot-INT-01.md).

Lần tiếp tục buổi sáng xác minh source/runtime fingerprint còn khớp hoàn toàn; giữ tám cặp đã đạt, lưu khóa cũ và tạo attempt mới cho phần planning chưa hoàn tất. Lần boot sau có LastBootUTC=2026-10-20T01:03:59.500Z; không thấy Event 41/6008 mới trong cửa sổ kiểm tra tương ứng, nên không suy diễn rằng có một reboot bất thường thứ hai. Một lần từ chối khởi động vì cổng 2000 bận cũng được giữ lại; chỉ chạy lại sau khi xác minh không còn process sở hữu cổng.

Telemetry của các attempts được chọn ghi GPU tối đa 65°C, VRAM tối đa 5.936/6.144 MiB, không chạm guard. Đây là các mẫu quan sát mỗi 5 s, không chứng minh mọi thời điểm đều dưới ngưỡng hoặc xác định nguyên nhân sự cố cũ. Không cập nhật driver/power settings. Kết thúc đã dừng hết engine sở hữu và không còn batch.lock; dữ liệu lỗi/gián đoạn và legacy được giữ nguyên.
