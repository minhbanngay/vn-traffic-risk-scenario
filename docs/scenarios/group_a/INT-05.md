# INT-05 — Vượt rồi nhập lại quá sát phía trước

Nguồn: dòng INT-05 trong Excel. Khác INT-01: CF vẫn hoàn tất vượt và nhập lại PHÍA TRƯỚC, không giảm tốc nhường để nhập phía sau.

Khởi đầu: ego 25 km/h, xe máy 45 km/h ở làn trái, sau ego 8 m. Chọn tốc độ thử cao hơn INT-01 để đủ đường cho CF vượt hẳn trước khi nhập. Đây là tham số khởi đầu cần kiểm chứng, không lấy nhãn đạt của INT-01 áp sang.

Chung đoạn approaching; planner đóng băng tick xe máy vượt lên trước tâm ego 3,5 m. R bắt đầu nhập ngay. CF giữ làn trái và tiếp tục vượt cho tới khi khoảng hở thân xe phía trước ≥2,1 × max(tốc độ ego quan sát, tốc độ ego mục tiêu); dựng đường nhập 14 m tại vị trí thực sự bắt đầu. Cả hai dùng cùng quy tắc tốc độ actor: 45 km/h khi vượt/chờ, 38 km/h từ lúc bắt đầu nhập và trong tail; chỉ khác quyết định bắt đầu nhập.

Trạng thái: approaching → waiting_safe_gap → merging → settling → completed. Event: intervention, merge_started, merge_completed. R có thể chuyển waiting_safe_gap → merging ngay cùng tick. Chỉ báo hoàn tất khi lệch ngang ≤0,35 m, lệch hướng ≤2° và không còn trôi ra xa tâm làn; không coi lần đi ngang qua tâm làn đầu tiên là ổn định. Mọi merge phải kết thúc trong vùng non-junction 80 m; route 130 m dành tail.

Nghiệm thu phiên bản 1:

- Quan sát được xe máy từ phía sau vượt lên phía trước.
- R nhập trước ego, headway dương <1 s khi overlap hành lang, liên tục ≥0,15 s; ego phanh và giảm ≥3 km/h trong 2 s sau trigger.
- CF nhập trước với headway ≥2 s trong mọi frame overlap từ lúc nhập; không hazard/ego trigger. Không chấp nhận CF nhập phía sau.
- Không collision; merge hoàn tất với sai lệch ngang ≤0,35 m, tail ≥4 s, không quay lại waypoint.
- Giữ các invariant pairing/recording/repeatability của schema 2.

Pilot: xe máy 45 km/h × khoảng sau ego 6/8/10 m. Timing thử hữu hạn lead 3,5/2,5 m; không thay ngưỡng nghiệm thu. Baseline 45 km/h, sau 8 m chạy ba lần. Site phải qua rehearsal CF + tail ở từng pair.

Thử thật revision 1 (`P-e82e1f52312e/A000001`) bị từ chối: tốc độ 45 km/h xuyên merge khiến overshoot sau completion khoảng 0,43 m ở cả R/CF, lớn hơn 0,35 m. Revision 2 giảm mục tiêu actor khi nhập về 38 km/h cho cả hai nhánh; vẫn giữ tốc độ ban đầu 45 km/h, cùng ngưỡng nghiệm thu và giữ nguyên output bị từ chối. Batch ID mới `int_05_pilot_v2`.

Revision 2 (`P-aaef1ad578a3/A000001`) vẫn bị từ chối ở R: overshoot khoảng 0,351 m sau khi báo completion; CF mất engine ở reload trước thu ảnh, lỗi hạ tầng riêng, không phải CF an toàn/không an toàn. Revision 3 bổ sung trạng thái settling/hướng/vận tốc ngang trước completion, và giảm khoảng hở LẬP KẾ HOẠCH CF từ 2,4 xuống 2,1 s để chừa đường ổn định trong vùng 80 m cho matrix 6–10 m. Ngưỡng NGHIỆM THU CF vẫn ≥2 s, lệch ngang vẫn ≤0,35 m xuyên tail. Cần chạy lại; batch ID `int_05_pilot_v3`.
