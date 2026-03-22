# Báo cáo Giai đoạn 2 — Thu thập dữ liệu Last.fm (Implicit Feedback)

**Môn:** CSC14114 — Ứng dụng dữ liệu lớn  
**Đồ án:** Recommendation System with Implicit Feedback  
**Dataset tự thu thập:** Last.fm — User × Artist (binary + playcount metadata)

---

## 1. Mục tiêu theo đề bài

Theo *Course Project [VI]*, Giai đoạn 2 yêu cầu:

- Thu thập **một dataset** có quy mô **tương đương MovieLens 1M** về mặt **ít nhất 1.000.000 tương tác**.
- Xác định **số lượng users và items** phù hợp nguồn.
- **Phác thảo schema** dự kiến.
- **Thu thập, làm sạch, chuẩn hóa** (trùng lặp, định danh, v.v.).
- Báo cáo có **pipeline**, **thống kê**, **khó khăn**.

**Kết quả đạt được:** Sau làm sạch có **1.677.243** tương tác (≥ 1M), **380 users**, **136.893 items** (artist).

---

## 2. Nguồn dữ liệu và phạm vi

| Hạng mục | Nội dung |
|----------|----------|
| **Nguồn** | Last.fm Web Service API (`ws.audioscrobbler.com`) |
| **Domain** | Gợi ý âm nhạc (implicit: có trong thư viện = quan sát) |
| **User** | Tài khoản Last.fm (username) |
| **Item** | Nghệ sĩ (artist), ưu tiên định danh MBID, fallback tên chuẩn hóa |
| **Tín hiệu thô** | `library.getArtists` — playcount trong thư viện |
| **Mô hình hóa** | Cạnh nhị phân `(user, artist)` với `label=1`; giữ `playcount` làm metadata |

**Quota / hạn chế:** API có rate limit; pipeline có backoff, cache HTTP, log từng request; giới hạn tải (bytes) cấu hình trong `config.yaml` để kiểm soát.

---

## 3. Pipeline thu thập và xử lý

Sơ đồ logic (Mermaid — có thể render trên GitHub / VS Code / [mermaid.live](https://mermaid.live)):

Xem file: `phase2_lastfm/docs/pipeline.mmd` (bản copy trong `reports/phase2/pipeline.mmd`).

**Tóm tắt các bước:**

1. **Khởi tạo:** Danh sách seed users (`data/seeds/seed_users.txt`).
2. **Mở rộng mạng:** `user.getFriends` theo BFS, giới hạn `max_users` (ví dụ 20.000 user đã “nhìn thấy”).
3. **Thu thập tương tác:** Với từng user trong queue, gọi `library.getArtists` (phân trang), lưu JSON thô vào `data/raw_api/`.
4. **Dừng crawl:** Khi đạt ngưỡng raw edges / ước lượng cleaned edges / quota / hết queue (theo `config.yaml` và tham số CLI).
5. **Làm sạch:** Đọc toàn bộ trang thư viện đã lưu → chuẩn hóa user/artist → dedup `(user, item)` → **k-core lặp** (`min_user_interactions`, `min_item_interactions`).
6. **Xuất model-ready:** `interactions.csv`, `users.csv`, `items.csv`, `interactions_binary.tsv`, `manifest.json` (checksum SHA-256).

**Công cụ:** Python, `requests`, `pandas`, `yaml`; trạng thái crawl có thể resume (`resume_state.json`).

---

## 4. Schema dữ liệu (sau xử lý)

### 4.1 `interactions.csv`

| Cột | Kiểu / Ý nghĩa |
|-----|----------------|
| `user_id` | ID nội bộ (0…N-1), ánh xạ từ username chuẩn hóa |
| `item_id` | ID nội bộ artist |
| `label` | `1` = quan sát (implicit positive) |
| `playcount` | Số lần nghe trong thư viện (metadata) |
| `crawl_timestamp_utc` | Thời điểm crawl trang tương ứng (ISO-8601) |

### 4.2 `users.csv` / `items.csv`

Chứa ánh xạ ID ↔ định danh chuẩn hóa (username, artist key / MBID / tên).

### 4.3 `interactions_binary.tsv`

Định dạng gọn cho huấn luyện graph CF (user, item, label).

---

## 5. Thống kê mô tả (sau làm sạch)

*Nguồn số liệu: `data/processed/manifest.json`, `docs/phase2_report_assets/summary_stats.json` (cập nhật sau lần build 2026-03-19).*

| Chỉ số | Giá trị |
|--------|--------:|
| Dòng raw (trước dedup gần đúng) | 2.351.922 |
| Sau dedup | 2.321.257 |
| **Tương tác sau k-core** | **1.677.243** |
| **Số users** | **380** |
| **Số items (artist)** | **136.893** |
| Mật độ ma trận (ước lượng) | ~3,22% |
| TB tương tác / user | ~4.414 |
| TB user / item | ~12,25 |
| Degree user (min / max) | 5 / 49.756 |
| Degree item (min / max) | 3 / 327 |
| Khoảng thời gian crawl (UTC) | 2026-03-16 → 2026-03-18 |

**Hình minh họa phân bố degree:**  
`phase2_lastfm/docs/phase2_report_assets/degree_hist_users.png`, `degree_hist_items.png`.

**Bảng tóm tắt:** `stats_table.md`, `stats_table.csv`.

---

## 6. So sánh với MovieLens 1M (theo đề)

| Khía cạnh | MovieLens 1M (tham chiếu đề) | Dataset Last.fm (nhóm) |
|-----------|------------------------------|-------------------------|
| Tương tác | ~1.000.000 | **1.677.243** (sau clean) |
| Users | ~6.000 | **380** |
| Items | ~4.000 (phim) | **136.893** (artist) |
| Cấu trúc | Users và items **cùng bậc nghìn** | **Rất nhiều item, ít user** (crawl BFS + full library/user) |
| Ngữ nghĩa | Rating / tương tác phim | Thư viện artist + playcount |

**Giải thích khác biệt cấu trúc:**

- MovieLens là bộ **benchmark** đã lọc với nhiều user cùng đánh giá một tập phim nhỏ hơn nhiều so với “mọi entity có thể có trên nền tảng”.
- Last.fm: mỗi user có thể có **hàng nghìn** artist trong thư viện → tổng số **item khác nhau** rất lớn dù chỉ ~400 user được crawl **đầy đủ** thư viện.
- Điều này **không vi phạm** yêu cầu “≥ 1M tương tác” nhưng cần **ghi rõ trong thực nghiệm Phase 3**: độ lệch user/item ảnh hưởng đến độ thưa, cold-start item, và so sánh metric giữa các dataset.

---

## 7. Khó khăn và cách xử lý

Chi tiết đầy đủ: `phase2_lastfm/docs/phase2_report_assets/difficulty_log.md`.

**Tóm tắt:**

1. **API key / lỗi 10:** Cần key hợp lệ; pipeline báo lỗi rõ nếu key sai.  
2. **Quota bytes / rate limit:** Tăng `approved_quota_max_bytes`, backoff, cache; crawl từng dừng khi đủ ước lượng cleaned edges.  
3. **Windows file lock khi ghi JSON:** Ghi `fsync` + retry atomic rename.  
4. **User không tồn tại / “no such page”:** Bỏ qua user, ghi log.  
5. **Bias mạng bạn bè:** Dữ liệu không ngẫu nhiên toàn Last.fm — thừa nhận trong báo cáo.  
6. **MBID / trùng tên artist:** Chuẩn hóa key ưu tiên MBID.  
7. **Không có timestamp theo từng interaction chi tiết** từ `library.getArtists` — chỉ có metadata crawl; có thể mở rộng `user.getRecentTracks` sau.

---

## 8. Tái lập kết quả (reproducibility)

Từ thư mục `phase2_lastfm/`:

```bash
# Crawl (cần LASTFM_API_KEY hoặc config/api_key.txt)
python -m src.collect.crawl_network --config config/config.yaml --seeds data/seeds/seed_users.txt --target-raw-interactions <TARGET>

# Làm sạch
python -m src.clean.build_interactions --config config/config.yaml --raw-dir data/raw_api --out-dir data/processed

# Thống kê & hình
python -m src.report.compute_stats --input data/processed/interactions.csv --out-dir docs/phase2_report_assets
```

Chi tiết: `phase2_lastfm/README_phase2.md`.

---

## 9. Kết luận

- Đã xây dựng **pipeline có sơ đồ**, **đủ ≥ 1.000.000 tương tác** sau làm sạch, **schema rõ ràng**, **thống kê và hình ảnh** trong `docs/phase2_report_assets/`.
- Cấu trúc **khác MovieLens 1M** (ít user, nhiều item) được **làm rõ** để phục vụ phân tích Phase 3.
- Sẵn sàng dùng làm **dataset thứ 5** trong 15 thí nghiệm (4 dataset chuẩn + 1 tự thu thập), sau khi tích hợp loader vào mã huấn luyện.

---

*Tài liệu slide gợi ý (20 phút): `PHASE2_SLIDES_OUTLINE.md`.*
