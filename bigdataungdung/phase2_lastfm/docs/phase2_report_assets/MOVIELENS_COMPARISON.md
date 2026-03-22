# So sánh dataset Last.fm (tự thu thập) với MovieLens 1M

| Chỉ số | MovieLens 1M (tham chiếu đề CSC14114) | Last.fm — sau làm sạch |
|--------|----------------------------------------|-------------------------|
| Tương tác | ~1.000.000 | **1.677.243** |
| Users | ~6.000 | **380** |
| Items | ~4.000 (phim) | **136.893** (artist) |
| Tỷ lệ Users/Items | ~1.5 | ~0.0028 |
| Đặc điểm | Nhiều user, ít item tương đối | Ít user (crawl đủ thư viện), **cực nhiều item** |

**Kết luận ngắn:** Đủ điều kiện **≥ 1M tương tác**. Khác biệt cấu trúc là **dự kiến** với phương pháp BFS + full `library.getArtist` và bản chất “mỗi user có hàng nghìn artist”.
