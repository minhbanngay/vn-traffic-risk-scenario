# Lộ trình danh mục 20 tình huống

Danh mục đầy đủ, mô tả R và CF cùng nhóm gốc nằm trong `configs/catalog.yaml`. INT-01 và các tình huống đợt 2 (INT-03/05/08) có implementation; trạng thái implemented không đồng nghĩa đã nghiệm thu dữ liệu. Tiến độ đợt 2 ở [báo cáo riêng](wave-2.md).

| Đợt | ID | Năng lực |
|---|---|---|
|1|INT-01|Pairing, cut-in, recording, risk, evaluation|
|2|INT-03, INT-05, INT-08|Ép ngang, vượt xe, phanh lead actor|
|3|INT-02, INT-04, INT-06, INT-07|Supporting actors, hàng xe, lane drop, trạm bus|
|4|INT-09, INT-10|Pedestrian/cyclist controllers|
|5|INT-11…INT-15|Junction routes, conflict region, quyền ưu tiên|
|6|INT-16, INT-17|Actor chính trong nhóm, can thiệp phối hợp, tín hiệu|
|7|INT-18…INT-20|Vòng xuyến, đường cong, hướng lưu thông|

Mỗi ID: đặc tả → site/blueprint preflight → một cặp → hiệu chỉnh có giới hạn → batch nhỏ → nghiệm thu → mở rộng. INT-16 phải chỉ rõ primary actor và những supporting actors cùng chịu can thiệp. Site đặc thù phải xác minh trên map trước khi công bố hỗ trợ.

Đợt 1 chỉ được đóng khi có 10 cặp đạt và ba baseline tái lập. Weather augmentation, random background traffic và sensor mới chờ các đợt sau.

Ngày 20/10/2026: mốc pilot INT-01 đã đạt 10/10 cặp, ba baseline với event spread 0 s, audit đủ 24 video / 6.425 ảnh và 76 test qua. Xem [báo cáo pilot](pilot-INT-01.md).

Ngày 21/10/2026: bắt đầu đợt 2, triển khai INT-03/05/08 với config, state machine, nghiệm thu và batch nhỏ riêng; bộ test tăng lên 126 test qua. INT-03 có một cặp mẫu đạt tự động, INT-05/08 còn hiệu chỉnh và chưa đạt cấp pair. Các tình huống cần supporting actor, pedestrian/junction/roundabout vẫn planned. Chỉ đánh dấu nghiệm thu dữ liệu sau CARLA/video và batch/repeat đầy đủ.
