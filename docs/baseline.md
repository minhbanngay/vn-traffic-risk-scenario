# Đối chiếu bản thử legacy

Kiểm tra ngày 2026-10-19: nhóm test thuần config/control/math/risk có 11 passed, 1 failed, 1 deselected. Lỗi do test output path hard-code V008 trong khi YAML dùng V009; test mới dùng fixture độc lập.

Các episode V002–V009 đều có một frame không có RGB. V009/risk: 171 frame, 13 risk frame, không collision, khoảng cách tâm tối thiểu khoảng 3,503 m. Cả 13 nhãn risk chỉ có reason `current_distance`.

Phép đối chiếu xấp xỉ theo ego heading cho thấy risk interval 176169–176181 kết thúc trước lateral footprint overlap đầu tiên khoảng frame 176186. Vì thế kết luận risk không được kiểm chứng chỉ từ center distance. V2 dùng footprint có heading và ghi số đo theo hành lang, cùng kiểm tra hành vi độc lập.

Nguyên nhân thiếu RGB legacy chưa được kết luận từ dữ liệu cũ. V2 log từng frame nhận/timeout và warm-up trước thu; chỉ số missing RGB là cổng nghiệm thu, không tự bỏ frame thiếu khỏi episode.

## Phát hiện từ cohort có giám sát ngày 20/10

Attempt `outputs/v2/INT-01/P-f3a65875cba3/A000001`, CF: có 349 dòng thu chính nhưng một dòng không có ảnh. Log ghi `rgb_timeout(frame_id=241)` ở event index 193, ngay sau đó `rgb_received(frame_id=241)` ở index 194. Như vậy callback frame này có đến, nhưng đến sau cửa sổ chờ 3 s của consumer. Buffer không gắn bù ảnh muộn vào dòng đã ghi thiếu; attempt bị loại đúng cổng recording, không xóa dòng, chèn ảnh thay thế hoặc sửa nhãn.

Attempt A000002 của cùng cặp thu đủ 349 ảnh CF và đạt toàn bộ kiểm chứng; R có 221 ảnh, prefix error=0. Cả attempt lỗi và attempt đạt đều được giữ. Công cụ giải mã video bổ sung được chuyển sang chạy sau khi thu để giảm tải đồng thời; chưa đủ bằng chứng coi tải đó là nguyên nhân duy nhất của callback trễ.

Phát hiện này giải thích một lỗi v2 quan sát được, không tự chứng minh nguyên nhân của ảnh thiếu ở toàn bộ episode legacy. Các output legacy không có log đồng bộ tương ứng để kết luận hồi tố. Một hướng nâng cấp sau pilot là spool ảnh callback muộn theo đúng frame để reconcile trước finalize, vẫn phải giữ timeout log và tuyệt đối không chấp nhận frame thực sự không đến.
