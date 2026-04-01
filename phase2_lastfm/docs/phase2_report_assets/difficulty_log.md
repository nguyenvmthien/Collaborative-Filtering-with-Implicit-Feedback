# Phase 2 — Nhật ký khó khăn & cách xử lý

## API quota và phê duyệt sử dụng

- **Rủi ro:** Vượt quota tải (bytes) hoặc số request; vi phạm điều khoản API nếu crawl quá lớn không kiểm soát.
- **Ảnh hưởng:** Crawl dừng giữa chừng; mất thời gian chờ reset hoặc phải chạy lại.
- **Giảm thiểu:** Cấu hình `approved_quota_max_bytes` / `approved_quota_max_requests` trong `config.yaml`; backoff + retry mã lỗi 29; cache HTTP để không tải lại trang đã có; state resume (`resume_state.json`); file `legal_clearance.json` ghi nhận bối cảnh học thuật.
- **Trạng thái:** Đã áp dụng; crawl dừng có kiểm soát khi đạt ngưỡng cleaned estimate / quota.

## Rate limit và lỗi tạm thời

- **Rủi ro:** HTTP 429/5xx, lỗi API 11/16/29 (overload, service unavailable).
- **Ảnh hưởng:** Request thất bại, làm chậm pipeline.
- **Giảm thiểu:** `rate_limit_rps` trong config; exponential backoff + jitter; retry có giới hạn; ghi `logs/api_calls.jsonl`.
- **Trạng thái:** Client đã triển khai theo config.

## Bias lấy mẫu theo mạng bạn bè (BFS)

- **Rủi ro:** User chỉ mở rộng từ seed + friends → không đại diện toàn bộ Last.fm.
- **Ảnh hưởng:** Phân bố degree, genre, hành vi lệch so với “ngẫu nhiên toàn nền tảng”.
- **Giảm thiểu:** Ghi rõ trong báo cáo; có thể thêm seed đa dạng / crawl ngẫu nhiên (hướng mở rộng).
- **Trạng thái:** Đã ghi nhận trong báo cáo Phase 2.

## Thiếu MBID và nhập nhằng tên artist

- **Rủi ro:** Cùng tên khác người; MBID rỗng.
- **Ảnh hưởng:** Trùng/ghép sai entity nếu chỉ dùng tên thô.
- **Giảm thiểu:** Chuẩn hóa `canonical_artist_key`: ưu tiên MBID, fallback tên chuẩn hóa; dedup theo cặp `(user_key, artist_key)`.
- **Trạng thái:** Đã tích hợp trong `normalize_entities` + bước build.

## Giới hạn timestamp (`library.getArtists`)

- **Rủi ro:** Endpoint không cung cấp lịch sử theo từng lần nghe chi tiết như implicit theo thời gian.
- **Ảnh hưởng:** Khó làm split theo thời gian chính xác ở mức interaction; chỉ có `crawl_timestamp_utc` / metadata crawl.
- **Giảm thiểu:** Ghi nhận trong báo cáo; tùy chọn mở rộng pass 2 với `user.getRecentTracks` nếu cần.
- **Trạng thái:** Chấp nhận cho Phase 2; mở rộng sau nếu đề tài yêu cầu.

## API key không hợp lệ (lỗi 10)

- **Rủi ro:** Key sai hoặc chưa cấu hình.
- **Ảnh hưởng:** Toàn bộ request 403, không có dữ liệu.
- **Giảm thiểu:** Biến môi trường `LASTFM_API_KEY` hoặc `config/api_key.txt`; pipeline fail-fast với thông báo rõ.
- **Trạng thái:** Đã xử lý trong code.

## Ghi file trên Windows (PermissionError)

- **Rủi ro:** `os.replace` tmp→json bị khóa bởi antivirus/OS.
- **Ảnh hưởng:** Crawl crash giữa chừng.
- **Giảm thiểu:** `flush` + `fsync` trước rename; retry với backoff ngắn.
- **Trạng thái:** Đã sửa trong `write_raw_page`.

## User không tồn tại / “no such page” (lỗi 6)

- **Rủi ro:** Username trong queue không còn hợp lệ trên API.
- **Ảnh hưởng:** Bỏ qua user đó.
- **Giảm thiểu:** Log `user_skipped_after_error` trong `crawl_progress.jsonl`; tiếp tục queue.
- **Trạng thái:** Đã xử lý.
