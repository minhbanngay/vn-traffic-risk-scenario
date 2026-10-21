# INT-01 — Abrupt motorcycle cut-in

Nguồn: Sheet1, dòng INT-01 của workbook trong `docs/sources`. R: xe máy vào trước ego với khoảng hở không đủ. CF: cùng xe máy chờ khoảng trống an toàn trước khi nhập làn. Implementation CF nhường cho ego vượt qua rồi nhập phía sau.

Baseline: Town10HD_Opt/ClearNoon, Tesla Model 3 25 km/h, Yamaha YZF 38 km/h, ở làn trái và sau ego 8 m. Blueprint fallback phải được resolve một lần cho cả cặp. Timestep/camera 0,05 s; RGB JPEG 1280×720, quality 85.

## Quyết định và trạng thái

approaching → intervention → R: merging → completed; CF: yielding → merging → completed.

Điều kiện quyết định dùng khoảng cách dọc tương đối: khi xe máy tiến lên trước ego bằng decision_lead_m. Planner diễn tập đoạn tiếp cận chung và đóng băng tick đạt điều kiện vào layout. Hai nhánh dùng cùng tick này và vẫn phải đạt kiểm tra prefix thực tế. R bắt đầu chuyển làn ngay. CF giảm về 10 km/h; khi đủ khoảng hở phía sau ego, tăng mục tiêu lên 18 km/h và dựng đường chuyển làn tại vị trí đang chạy. Ngưỡng CF tính theo tốc độ dự kiến lúc nhập, tránh nhập sát chỉ vì tốc độ lúc chờ thấp.

Đường chuyển làn dài 14 m dùng smoothstep theo tiến độ dọc route. Chỉ hoàn thành khi vượt cuối đoạn chuyển làn và sai lệch ngang dưới 0,35 m. Route phải đủ cho phần ghi tiếp 4 s; route hết hoặc maneuver ra ngoài vùng cho phép làm episode incomplete/failed.

Town10HD không có đoạn hai làn thẳng liên tục 130 m ngoài giao lộ theo preflight. Vùng maneuver phải nằm trong 80 m đầu có hai làn cùng chiều, không junction; phần route 130 m còn lại phục vụ ghi sau maneuver, có thể đi thẳng qua junction. Không cho bắt đầu một chuyển làn không thể hoàn tất trong vùng maneuver. Đây là điều chỉnh placement từ kết quả kiểm tra map; mọi lần chạy lưu route thực để kiểm chứng.

Config revision 2 mở vùng đã xác minh từ 70 lên 80 m và dùng tail 4 s thay vì 5 s để dành đủ route cho các sample bắt đầu xa hơn. Kiểm tra OpenDRIVE trực tiếp có ít nhất một candidate cho mọi khoảng cách 6–10 m ở vùng 80 m, nhưng không có ở 90 m. Planner còn diễn tập vật lý toàn bộ CF và tail trước thu ảnh; chỉ layout vượt qua bước này mới được chạy R–CF. Đây là thay đổi bố trí/thời lượng trong giới hạn plan, không thay các ngưỡng nghiệm thu phiên bản 1.

## Ego và nhãn

Hai nhánh dùng cùng detector footprint/constant-velocity prediction. Ego trễ 0,5 s khi phát hiện hazard, giảm mục tiêu về 12,5 km/h, brake tối đa 0,15, giữ thấp 0,75 s và tự phục hồi; timeout giảm tốc 3 s như bản thử.

Risk detector xét overlap ngang trong hành lang và khoảng hở dọc/headway hiện tại hoặc dự đoán 1,5 s. Khoảng cách tâm chỉ là số đo phụ. Collision được đối chiếu theo frame khi finalize.

## Nghiệm thu phiên bản 1

- Prefix sai lệch vị trí ≤0,10 m và vận tốc ≤0,10 m/s; cùng bước intervention.
- R nhập trước ego, headway dương <1 s liên tục ≥0,15 s khi overlap hành lang.
- Ego có phanh và giảm ≥3 km/h trong 2 s sau trigger.
- CF nhập phía sau, headway ≥2 s và không gây hazard/ego trigger.
- Không collision; maneuver hoàn tất và ghi đủ phần đuôi.
- Ảnh đủ, đúng frame và đọc được; Risk Tube có validity mask đúng.
- Baseline ba lần đều đạt, các mốc thời gian lệch ≤0,15 s.

Batch gồm 36/38 km/h × khoảng cách sau ego 6/7/8/9/10 m. Timing được thử hữu hạn ở lead 2,5/3,5/4,5 m, không sửa ngưỡng nghiệm thu trong quá trình thử. Kết quả fail được giữ để phân tích, không tính vào 10 cặp đạt.
