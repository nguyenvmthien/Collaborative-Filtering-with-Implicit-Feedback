# Outline trình bày Phase 2 (≤ 20 phút) — Last.fm Dataset

**Gợi ý:** ~12–14 slide, ~1–1,5 phút/slide; chừa 2–3 phút cho demo / hỏi đáp ngắn.

---

## Slide 1 — Tiêu đề (30 giây)
- Tên môn, đồ án, tên nhóm
- **Phase 2: Thu thập dữ liệu — Last.fm (User × Artist, Implicit Feedback)**

## Slide 2 — Mục tiêu đề bài (1 phút)
- ≥ 1.000.000 tương tác
- Dataset tự thu thập + làm sạch + chuẩn hóa
- So sánh quy mô với MovieLens 1M (số tương tác; khác biệt user/item)

## Slide 3 — Bài toán & biểu diễn dữ liệu (1 phút)
- Implicit feedback: quan sát = 1
- Top-K recommendation (nối với Phase 1)
- Item = **artist**, không phải track

## Slide 4 — Nguồn & API (1 phút)
- Last.fm Web API
- Hai endpoint chính: `user.getFriends`, `library.getArtists`
- Hạn chế: rate limit, quota — pipeline có log + backoff + cache

## Slide 5 — Pipeline (diagram) (2 phút)
- **Chèn sơ đồ** từ `phase2_lastfm/docs/pipeline.mmd` (export PNG qua mermaid.live hoặc extension VS Code)
- Seed → BFS friends → queue → crawl library → raw JSON → clean → k-core → CSV/TSV

## Slide 6 — Schema (1 phút)
- Bảng: `user_id`, `item_id`, `label`, `playcount`, `crawl_timestamp_utc`
- File: `interactions.csv`, `users.csv`, `items.csv`, `interactions_binary.tsv`

## Slide 7 — Thống kê chính (1,5 phút)
- **1.677.243** interactions | **380** users | **136.893** items
- Density ~3,2%; TB ~4.414 interactions/user
- **Hình:** `degree_hist_users.png`, `degree_hist_items.png` (2 ảnh nhỏ trên 1 slide hoặc 2 slide)

## Slide 8 — Raw vs Processed (1 phút)
- Raw ~2,32M edges (unique) sau crawl; sau dedup + k-core → 1,67M
- K-core: user ≥ 5, item ≥ 3 (từ `config.yaml`)

## Slide 9 — So sánh MovieLens 1M (1,5 phút)
- Bảng 1 dòng: ML-1M (~1M, ~6k users, ~4k items) vs Last.fm (~1,67M, **380** users, **137k** items)
- **Thông điệp:** Đủ mốc 1M tương tác; cấu trúc lệch do crawl + semantics (library lớn/user)

## Slide 10 — Khó khăn 1: API & quota (1 phút)
- Invalid API key; quota bytes; rate limit
- Giải pháp: config quota, retry, resume state

## Slide 11 — Khó khăn 2: Kỹ thuật & dữ liệu (1 phút)
- Windows file lock; user “no such page”
- Bias mạng bạn bè; MBID / trùng tên

## Slide 12 — Hạn chế & hướng mở rộng (1 phút)
- Ít user vs ML-1M; có thể crawl thêm target / nhiều seed
- Optional: `user.getRecentTracks` cho timestamp
- Legal: `legal_clearance.json` (học thuật / quota)

## Slide 13 — Demo nhanh / Cấu trúc repo (1 phút)
- Tree: `phase2_lastfm/data/processed/`, `docs/phase2_report_assets/`
- Lệnh reproduce (1 dòng hoặc screenshot terminal)

## Slide 14 — Kết luận (30 giây)
- Đạt yêu cầu Phase 2 về quy mô tương tác + pipeline + thống kê
- Sẵn sàng tích hợp Phase 3 (5 datasets)

---

### Gợi ý khi dựng PowerPoint / Google Slides
- Font ≥ 18pt; sơ đồ pipeline **một trang**, ít chữ.
- Số liệu lấy từ `summary_stats.json` / `stats_table.csv` nếu cần cập nhật sau này.
- Giữ **1 slide so sánh MovieLens** để trả lời trước câu hỏi của GV.
