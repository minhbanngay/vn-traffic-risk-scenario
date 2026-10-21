# Kiến trúc R–CF, schema 2

CLI → resolve defaults/scenario/batch → pair planner → frozen layout → hai episode R/CF → evaluator → batch report.

`core` sở hữu cấu hình, registry, vòng lặp, định danh cặp và batch. `runtime` quản lý CARLA world, actor và callback sensor. `geometry` cung cấp phép chiếu route theo chiều dài và footprint. `behaviors` dùng lại controller PI/PD và phản ứng ego. `scenarios/group_a` chứa INT-01/03/05, `scenarios/group_b` chứa INT-08. `evaluation` tách annotation khỏi nghiệm thu. `recording` giữ dữ liệu thô, dữ liệu hoàn thiện, video và trang review.

## Bản đồ các module chính

Đường dẫn dưới đây tương đối với `src/vn_traffic_risk/`. Các `__init__.py` chỉ đánh dấu package hoặc export API.

| Module | Hàm/lớp chính | Đầu vào → đầu ra |
|---|---|---|
| `cli.py`, `__main__.py` | `main` | Phân luồng subcommand mới và CLI legacy |
| `core/cli.py` | `main` | Tham số dòng lệnh → config/run/evaluation |
| `core/config.py` | `load_pair_config`, `merge`, `validate`, `PairConfig.branch`, các fingerprint | YAML và overrides → cấu hình chung/nhánh đã kiểm tra |
| `core/models.py` | `Scenario`, `ScenarioStep`, `decode_actor` | Hợp đồng scenario; states JSON → ActorState |
| `core/registry.py` | `get_scenario`, mode/matrix/calibration contracts | INT-01/03/05/08 → implementation tương ứng; 16 ID planned chưa có executor |
| `core/pairing.py` | `allocate_attempt`, `run_pair` | Cấu hình chung → attempt mới, frozen layout, R/CF, báo cáo |
| `core/worker.py` | `main` | Payload JSON → readiness, planner hoặc một episode trong process riêng |
| `core/runner.py` | `run_episode` | Session/config/layout → vòng tick, recorder, cleanup và video |
| `core/batch.py` | `expand_batch`, `run_batch`, `evaluate_repeats` | Ma trận → cặp, calibration, resume và baseline repeatability |
| `runtime/session.py` | `PairSession`, `ActorScope`, `spawn_exact` | Quản lý world; spawn đúng layout và đăng ký cleanup ngay |
| `runtime/server.py` | `ManagedServer`, `server_scope` | Config server → engine do runner sở hữu hoặc external scope |
| `runtime/commands.py` | `apply_controls`, `initialize_motion` | Điều khiển/vận tốc ban đầu → lệnh CARLA batch có ACK |
| `runtime/sensors.py` | `RGBFrameBuffer`, `attach_sensors` | Callback bất đồng bộ → RGB tra theo frame và log chẩn đoán |
| `geometry/routes.py` | `RoadRoute.at/station/lateral/forward` | Route/điểm thế giới → waypoint và tọa độ theo đường |
| `geometry/footprints.py` | `footprint`, `corridor_metrics` | ActorState → thân xe, khoảng hở, headway và TTC |
| `behaviors` | `SimpleVehicleController`, `EgoRiskResponse` | Target waypoint/speed và hazard hiện tại → control/phản ứng ego |
| `behaviors/controllers.py` | `vehicle_controller` | Gain actor trong config → controller cho actor; ego giữ gain mặc định chung |
| `scenarios/group_a/int_01_cut_in.py` | `find_sites`, `CutInScenario.plan/freeze_intervention/initialize/step` | Map/config/states → layout, quyết định cut-in/nhường, sự kiện |
| `scenarios/straight_road.py` | `StraightRoadScenario.plan/freeze_intervention/finish_step` | Site, rehearsal CF, route/zone/tail cho đợt 2; không thay state machine INT-01 |
| `scenarios/group_a/int_03_lateral_squeeze.py` | `LateralSqueezeScenario.step` | Song song → ép ngang/tách ra hoặc giữ khoảng cách |
| `scenarios/group_a/int_05_overtake.py` | `OvertakeScenario.step` | Vượt → nhập sát hoặc chờ đủ gap phía trước |
| `scenarios/group_b/int_08_lead_braking.py` | `LeadBrakingScenario.step` | Lead cùng làn → phanh gấp trễ/phanh nhẹ sớm → phục hồi |
| `scenarios/wave2_config.py` | `validate_wave2` | Tham số → kiểm tra ràng buộc vật lý riêng, không cần CARLA |
| `evaluation/scenario_checks.py` | `check_wave2`, `completion_events` | Frame/event → tiêu chí ngang, vượt, phanh và tail riêng |
| `evaluation/risk.py` | `observe`, `future_vectors` | Hình học/trạng thái → nhãn hiện tại và Risk Tube có mask |
| `evaluation/validation.py` | `evaluate_episode`, `evaluate_pair` | Dữ liệu đã ghi → kiểm chứng độc lập, failures và metrics |
| `recording/recorder.py` | `EpisodeRecorder`, `write_json`, `read_jsonl` | RGB/states/events → dữ liệu thô bền vững và episode hoàn thiện |
| `recording/report.py` | `write_review` | Hai episode → HTML hai video và biểu đồ |
| `video.py` | `create_video` | Danh sách RGB trong frames.jsonl → episode.mp4; dùng chung legacy/v2 |

Các file phẳng `scenario.py`, `placement.py`, `risk.py`, `recorder.py`, `sensors.py`, `config.py` là đường legacy, không phải bản trùng của schema 2. `actors.py`, `control.py`, `models.py`, `projection.py`, `math_utils.py`, `carla_runtime.py` là các tiện ích cũ vẫn được tái sử dụng có chọn lọc.

## Cấu hình và định danh

Defaults → scenario → sample trong batch → can thiệp của actor. `interventions` chỉ được chọn hai mode đăng ký; không được sửa ego, weather, camera hay spawn. Resolved configuration được deep-copy giữa hai nhánh. Cấu hình site được kiểm tra map và đưa selection vào cấu hình chung.

`pair_id` là hash của cấu hình chung đã resolve, gồm cả cấu hình can thiệp. Timing hiệu chỉnh khác tạo pair ID khác; batch dùng sample parameters để nhóm những lần hiệu chỉnh cùng mục tiêu. `attempt_id` tăng bằng thao tác tạo directory độc quyền. Mỗi lần chạy giữ manifest, source revision, thời điểm UTC và layout fingerprint. Không ghi đè output cũ.

`layout.json` đóng băng blueprint, spawn, map OpenDRIVE hash, route, vùng maneuver và lane metadata. Planner diễn tập riêng đoạn tiếp cận chung (không đưa vào dataset), rồi đóng băng `intervention_step_index` và trạng thái tham chiếu. Diễn tập tiếp hành vi CF đến hết tail để kiểm tra đủ đường trước khi thu ảnh. Cả R và CF dùng đúng tick quyết định này, không tự tìm lại tick từ một ngưỡng hình học dễ lệch do sai số vật lý. Evaluator vẫn kiểm tra sai lệch prefix thực tế; đóng băng tick không làm bỏ qua kiểm tra đối chứng. Trước mỗi nhánh, reload world để reset physics; môi trường ban đầu phải không có vehicle/walker do client khác tạo. Khi kết thúc, hủy tài nguyên theo thứ tự ngược và khôi phục settings/weather.

## Dữ liệu mỗi tick

Đọc actor states → scenario chọn waypoint/tốc độ → ego nhận hazard từ trạng thái hiện tại → batch VehicleControl có ACK → world.tick → snapshot/state/RGB cùng frame → footprint metrics → raw record và events. `apply_batch_sync(..., False)` xác nhận lệnh nhưng không tự tick; chỉ runner gửi một tick cho mỗi bước.

Frame chứa `schema_version`, scenario/pair/attempt/branch, `step_index`, CARLA `frame_id`, timestamp tuyệt đối và tương đối, ego, primary actor, supporting actors, control, maneuver state, RGB reference, box và risk. Actor ID CARLA không dùng để nối hai nhánh; dùng role name và step index.

Không dùng tên nhánh, ground-truth tương lai hay kết quả evaluator để quyết định phản ứng ego. Bộ detector dùng footprint và vận tốc quan sát được; nhãn risk hiện tại không đồng nghĩa chắc chắn xảy ra collision.

Đợt 2 dùng `ScenarioStep.brake_limits` để giới hạn phanh actor; runner ghi control thực tế như trước, không điều khiển ego theo nhánh. Chỉ cấu hình bật `lateral_clearance_m` (INT-03) hoặc `closing_ttc_seconds` (INT-08) mới thêm metric/lý do tương ứng. INT-01 giữ nguyên cấu hình và quy tắc nhãn. Registry hiện ánh xạ bốn ID; không sinh executor giả cho 16 ID còn planned.

## Recording và phục hồi

Warm-up cố định 40 tick cho cả diễn tập và hai nhánh; camera phải có ít nhất ba ảnh liên tiếp ở cuối warm-up, nếu không episode thất bại thay vì tự kéo dài warm-up. RGB buffer giữ ảnh tương lai, log received/duplicate/timeout. `frames.raw.jsonl` và `events.jsonl` flush mỗi tick. `frames.jsonl` được finalize nguyên tử sau đối chiếu collision callbacks đến muộn và gắn Risk Tube.

`collision_now` chỉ đúng ở frame có collision; `collision_occurred` đúng từ collision đầu tiên trở đi. Risk Tube H=8, bước 0,5 s, kèm `future_risk_valid`; giá trị 0 với validity=false là chưa quan sát, không phải nhãn an toàn.

`episode.json` có running/complete/incomplete/failed. Nếu process bị tắt bất ngờ, dữ liệu thô vẫn còn; evaluator từ chối trạng thái running. Đường dẫn attempt được checkpoint vào batch ngay sau cấp tên, trước khi engine khởi động. Resume batch tạo attempt mới cho lần lỗi/gián đoạn, không nối hai đoạn vật lý thành một episode. Batch lock ngăn hai runner cùng thao tác một batch; sau crash phải xác minh không còn runner trước khi lưu/loại khóa cũ, không tự xóa khóa đang tồn tại.

Video dùng encoder cũ, đọc đúng danh sách RGB trong frames.jsonl. `review.html` đặt hai video và biểu đồ cạnh nhau. `validation.json` là nguồn kết luận nghiệm thu, không dựa vào tên R/CF.

## Tương thích

Lệnh legacy `python -m vn_traffic_risk --config ... --variant risk` giữ nguyên. Chỉ các subcommand mới đi qua schema 2. `safe` cũ không được tự đổi thành CF. Dữ liệu `outputs/INT_MOTO_001` giữ nguyên.

## CARLA server riêng trên Windows

Batch `configs/batches/int_01_pilot_managed.yaml` bật `managed_server`. Planner, R và CF là các SDK worker riêng, chạy tuần tự; mỗi worker được một process engine mới để tránh lỗi bàn giao native episode subscription giữa process. Cùng frozen layout/config được replay trên các engine mới; tính đối chứng vẫn do evaluator kiểm chứng từ dữ liệu. Mỗi worker episode dùng một client, bật sync/fixed delta rồi reload world giữ nguyên settings trước khi tạo actor. Tiến trình điều phối chỉ sở hữu process/socket, không tạo CARLA client; engine chỉ dừng sau khi SDK worker thoát. Chế độ này cần cổng 2000 trống; nếu có server đang chạy thì từ chối, không dừng tiến trình đó. Chỉ process tạo bởi ManagedServer mới bị dừng trong cleanup.

Theo [CARLA physics determinism](https://carla.readthedocs.io/en/latest/adv_synchrony_timestep/#physics-determinism), sync/fixed delta phải có trước khi reload và được giữ bằng `reload_world(False)`. Tại mỗi thời điểm chỉ một episode worker gửi tick; worker khôi phục settings khi kết thúc để client kế tiếp có thể kết nối. Ego và actor dùng controller vật lý bình thường. Prefix được đo và kiểm chứng từ các trạng thái thực.

Đường dẫn mặc định trỏ tới shipping executable trong bản CARLA chứa project này. Có thể đặt `carla.server_executable` để dùng bản cài khác. Chế độ external vẫn là mặc định của `run-pair` và batch gốc; server phải đang sẵn sàng.

Manifest lưu hash toàn bộ Python implementation, Git revision, phiên bản Python/dependencies và hash binary CARLA. Code đổi giữa chừng làm lần chạy dừng; cấu hình, implementation hoặc runtime đổi khi resume yêu cầu batch ID mới. Baseline repeats phải có cùng các fingerprint này. Lỗi hạ tầng làm batch interrupted, không tiếp tục thử các timing như thể đó là thất bại hành vi.

## Chạy có giám sát và theo chặng

Owned engine nhận `carla.server_max_fps=20` bằng console command của engine. Đây là giới hạn tốc độ chạy theo thời gian thực, không thay bước mô phỏng/camera 0,05 s. `runtime/health.py` đọc GPU bằng nvidia-smi, không sửa thiết lập hệ thống; stage planner/R/CF ghi telemetry riêng trong attempt. Guard ngắt đúng process engine sở hữu khi GPU >=82°C, VRAM >=97%, hoặc ba lần probe lỗi liên tiếp. Các ngưỡng này là biện pháp thận trọng của dự án, không phải khẳng định giới hạn an toàn của hãng hoặc bảo đảm tránh reboot.

`run-batch --max-new-attempts 1` dừng sạch sau một pair attempt mới và checkpoint status=partial, không tự chạy các baseline. Resume bằng cùng lệnh bỏ giới hạn sẽ kiểm tra lại cặp đã chọn rồi chạy phần còn thiếu. Giới hạn thực thi này không đi vào fingerprint nội dung batch; thay physics/config/source/runtime vẫn cần batch ID mới.
