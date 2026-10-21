# INT-03 — Xe máy ép ngang khi chạy song song

Nguồn: dòng INT-03, Sheet1 trong Excel đã lưu ở `docs/sources`. Không bổ sung actor hoặc thay quyết định ego theo nhánh.

Khởi đầu: Tesla 25 km/h, xe máy 25 km/h ở làn trái, sau tâm ego 1 m (hai footprint chồng khoảng dọc). Town10HD_Opt/ClearNoon; camera và ego dùng defaults chung. Sau đoạn tiếp cận 2 s, planner đóng băng tick quyết định.

- R: dịch ngang bằng smoothstep 12 m, nhắm khoảng hở giữa thân xe 0,30 m; giữ 1 s rồi tách ra làn ban đầu trong 12 m. Khoảng hở mục tiêu tính theo footprint blueprint thực tế.
- CF: giữ làn và khoảng cách ngang; quan sát thêm 5 s rồi ghi tail 4 s.

Trạng thái R: approaching → squeezing → holding_clearance → separating → completed. CF: approaching → maintaining_clearance → completed. Event: intervention, maneuver_started, squeeze_reached, separation_started, maneuver_completed. Không gọi squeeze là nhập làn hoàn chỉnh.

Detector nhận vị trí/vận tốc/footprint hiện tại: nguy hiểm khi footprint chồng khoảng dọc và khoảng hở ngang <0,60 m, hoặc dự đoán xung đột bằng vận tốc quan sát trong 1,5 s. Không biết tên nhánh. Quy tắc headway chung vẫn áp dụng nếu xe lấn hẳn hành lang. Các metric ngang chỉ bổ sung ở cấu hình này, không thay nhãn INT-01 cũ.

Nghiệm thu phiên bản 1:

- Khoảng hở ngang dương nhưng <0,60 m khi chồng khoảng dọc, liên tục ≥0,15 s ở R. Không có khoảng hở ngang ≤0 khi hai footprint chồng khoảng dọc.
- R có ego trigger, lệnh phanh và giảm ≥3 km/h trong 2 s; không collision.
- CF giữ khoảng hở ngang ≥1 m, không hazard/ego trigger.
- R trở lại đúng làn trái; CF không rời làn. Sau hoàn thành, cả hai đi tiến trên route, sai lệch ngang ≤0,20 m, tail ≥4 s.
- Các invariant chung: frozen layout, ego config bằng nhau, prefix ≤0,10 m/0,10 m/s, RGB/frame, mask tương lai, ba baseline lệch mốc ≤0,15 s.

Pilot nhỏ: khoảng sau ego 0,5/1,0/1,5 m, tốc độ đều 25 km/h. Ngưỡng là tiêu chí dự án ban đầu, không phải tiêu chuẩn giao thông. Chưa công bố nghiệm thu nếu chưa có báo cáo CARLA đạt.
