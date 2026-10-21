# Dữ liệu kiểm thử

Fixture schema 2 được dựng trong `tests/conftest.py` vào thư mục tạm của pytest. Ảnh nhỏ và trạng thái vật lý tổng hợp chỉ phục vụ kiểm tra evaluator, không phải dữ liệu CARLA và không được nhập vào batch thật.

- `tests/unit`: config, danh mục Excel/checksum, hình học, state machine, tick can thiệp, lệnh batch, site rehearsal, world reset và owned-server scope.
- `tests/integration`: ghép recorder/sensor/evaluator, callback đến muộn, thiếu/trùng ảnh, ghi dở, engine/worker lifecycle, prefix drift, repeat context và resume.
- Các test tự động không cần CARLA server, không chứng minh đã có 10 cặp thật. Nghiệm thu thật đọc `outputs/v2/batches/<batch_id>/validation.json`, kiểm tra ba baseline và xem `review.html` của các cặp.

Không sao chép ảnh hoặc kết quả tổng hợp từ fixture vào `outputs/v2/INT-01` để làm dữ liệu đạt.
