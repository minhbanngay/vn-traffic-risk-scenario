# INT-08 — Xe máy dẫn đầu phanh đột ngột

Nguồn: dòng INT-08 trong Excel, giữ nguyên group_b. R phanh gấp; CF giảm tốc sớm hơn, nhẹ hơn. Không thay ego controller giữa hai nhánh.

Khởi đầu: hai xe 25 km/h cùng làn, xe máy phía trước tâm ego 24 m. Planner dùng vùng đường thẳng của INT-01 nhưng resolve lại spawn xe máy trên chính làn ego; không đặt xe máy ở làn trái. `site_search_rear_clearance_m` chỉ là khoảng trống dùng cho phép tìm site chung, không phải spawn actor.

Sau 2 s tiếp cận, planner đóng băng intervention:

- CF bắt đầu giảm mục tiêu ngay, theo ramp 0,7 m/s² xuống 18 km/h, không giữ tốc độ thấp, rồi tăng về 25 km/h với ramp 1,5 m/s². Brake tối đa 0,12 khi giảm tốc.
- R giữ tốc độ thêm 2 s, rồi ramp giảm 3,5 m/s² xuống 8 km/h, giữ 1 s và phục hồi cùng ramp 1,5 m/s². Brake tối đa 0,55 khi giảm tốc.

Ramp là mục tiêu điều khiển, KHÔNG giả định gia tốc vật lý bằng ramp. Evaluator đọc gia tốc/tốc độ/control thực tế. Actor phải đạt mục tiêu tốc độ rồi mới ghi braking_target_reached; phải phục hồi đủ tốc độ mới hoàn thành.

Trạng thái: approaching → anticipating → braking → holding_speed → recovering → completed. Event: intervention, maneuver_started, braking_started, braking_target_reached, recovery_started, maneuver_completed. CF braking_started phải sớm hơn R trong cùng pair.

Nhãn bổ sung: TTC dọc dương <3 s với xe máy phía trước, cùng hành lang; chỉ suy ra từ gap và closing speed hiện tại. Không đưa gia tốc tương lai hay nhánh vào detector ego. Nhãn headway hiện tại/dự đoán vẫn hoạt động.

Nghiệm thu phiên bản 1 (riêng INT-08, không dùng nhầm tiêu chí cut-in):

- R có TTC dương <3 s liên tục ≥0,15 s, gia tốc giảm dọc đỉnh ≥2 m/s² trong giai đoạn braking; ego có trigger/phanh và giảm ≥3 km/h trong 2 s.
- CF phanh sớm hơn R, giảm tốc thực tế ≥3 km/h, gia tốc giảm dọc đỉnh ≤1,5 m/s² trong braking, headway ≥1,8 s xuyên episode; không hazard/ego trigger.
- Cả hai cùng làn, actor luôn phía trước; không collision. Phục hồi và hoàn tất trong vùng 80 m, lệch ngang ≤0,35 m, tail ≥4 s đi tiến.
- Pairing/recording/mask/repeatability giữ invariant chung.

Pilot: khoảng trước ego 22/24/26 m, tốc độ 25 km/h. Baseline 24 m chạy ba lần. Các giá trị là tiêu chí ban đầu của dự án và phải được phiên bản hóa nếu cần sửa; chưa tuyên bố đạt chỉ từ unit test.

## Thử thật và việc còn lại

Revision 1: `outputs/v2/INT-08/P-b929b3b8e0c8/A000001` bị từ chối. R 272 frame đạt: TTC nguy hiểm 0,25 s, gia tốc giảm dọc đỉnh 4,409 m/s², ego giảm 12,158 km/h. CF 201 frame, không hazard/collision/thiếu RGB, nhưng gia tốc giảm đỉnh 4,839 m/s² >1,5 m/s² nên KHÔNG đạt. Prefix vị trí/vận tốc bằng 0.

Kiểm tra frame thật: CF step 39 đã có gia tốc giảm khoảng 4,20 m/s² trước intervention step 40; step 41 đạt đỉnh 4,839 m/s² dù lệnh brake=0 và throttle≈0,322. Đây là dao động vật lý/điều khiển đã xuất hiện trong đoạn tiếp cận; chưa đủ bằng chứng quy cho riêng chuyển số hay một gain cụ thể. Ramp mục tiêu nhẹ không bảo đảm gia tốc thực tế nhẹ.

Revision 2 chuẩn bị hiệu chỉnh: gain actor cấu hình riêng (mặc định vẫn 0,55/0,08/1,35/0,10, không tự nhận là đã tối ưu), giữ giới hạn phanh xuyên giai đoạn phục hồi, ghi thêm gear/manual_gear_shift của lệnh control. Ego không nhận gain actor hoặc tên nhánh. Chưa chạy lại revision này. Batch ID mới `int_08_pilot_v2`; ngưỡng gia tốc CF vẫn 1,5 m/s².

Evaluator tính mức giảm tốc từ tốc độ ngay trước braking_started đến tốc độ nhỏ nhất trong braking, không dùng transient lúc vừa gán vận tốc ở frame đầu để nhận nhầm CF đã giảm tốc. Không sửa nhãn hoặc metadata của attempt revision 1.

Bước tiếp theo: kiểm tra ổn định tốc độ/gia tốc trong common approach, thử controller/blueprint có giới hạn và phiên bản cấu hình riêng, xác minh CF giảm tốc nhẹ thật rồi mới chạy matrix/repeats. Chưa mở batch đầy đủ hoặc mở rộng sang người đi bộ/giao lộ.
