# Phase 1 - Nghiên cứu lý thuyết

## 1. Implicit Feedback vs Explicit Feedback

### Explicit Feedback (Tường minh)
- Người dùng **chủ động** đánh giá: chấm sao (1-5), viết review
- **Ưu điểm**: Tín hiệu rõ ràng, chính xác, ít cần suy diễn
- **Nhược điểm**: Dữ liệu ít (người dùng lười đánh giá), bị bias (chỉ những người có cảm xúc mạnh mới đánh giá), cold-start nặng hơn

### Implicit Feedback (Ngầm định)
- Người dùng **gián tiếp** thể hiện qua hành vi: click, xem, mua, nghe, thêm vào giỏ
- **Ưu điểm**: Dữ liệu phong phú, tự nhiên, không cần user effort
- **Nhược điểm**: Nhiễu (click nhầm), không rõ ràng (xem không có nghĩa là thích), thiếu negative signal rõ ràng

### Biểu diễn nhị phân 0/1
- **observed = 1**: User đã tương tác với item (click, mua, nghe...)
- **unobserved = 0**: User CHƯA tương tác — **KHÔNG có nghĩa là không thích**
  - Có thể user chưa biết đến item đó
  - Có thể user thấy nhưng không quan tâm
  - Có thể user muốn nhưng chưa có dịp
- Đây là điểm khó nhất của implicit feedback: phân biệt "không thích" và "chưa biết đến"

---

## 2. Top-K Recommendation

### Định nghĩa
Với mỗi user, hệ thống gợi ý K item có khả năng cao nhất user sẽ tương tác, thay vì dự đoán rating cụ thể.

### Quy trình
1. Tính điểm (score) cho tất cả items mà user chưa tương tác
2. Sắp xếp giảm dần theo score
3. Trả về K item đầu tiên

### Ví dụ
- K=10: Gợi ý top 10 phim cho user
- K=20: Top 20 sản phẩm user có thể mua

---

## 3. Evaluation Metrics

### a) Precision@K
```
Precision@K = |{relevant items trong top-K}| / K
```
- Đo "trong K item được gợi ý, bao nhiêu % là đúng"
- Nhược điểm: không phân biệt thứ tự trong top-K

### b) Recall@K
```
Recall@K = |{relevant items trong top-K}| / |{tất cả relevant items của user}|
```
- Đo "trong tất cả items user thích, bao nhiêu % được gợi ý"
- Thường dùng kết hợp với Precision (F1-score)

### c) Hit Rate@K (HR@K)
```
HR@K = 1 nếu có ít nhất 1 relevant item trong top-K, ngược lại = 0
(trung bình qua tất cả users)
```
- Đơn giản: có gợi ý đúng không?

### d) NDCG@K (Normalized Discounted Cumulative Gain)
```
DCG@K = sum_{i=1}^{K} rel_i / log2(i+1)
NDCG@K = DCG@K / IDCG@K
```
- Đo "đúng theo thứ tự" — item đúng ở vị trí càng cao càng tốt
- **Quan trọng nhất** trong thực tế, được dùng nhiều nhất

### e) MAP@K (Mean Average Precision)
```
AP@K = (1/R) * sum_{k=1}^{K} Precision@k * rel(k)
MAP@K = mean(AP@K) qua tất cả users
```
- Đo trung bình precision có tính đến thứ tự

### f) MRR@K (Mean Reciprocal Rank)
```
RR = 1 / rank_của_item_đúng_đầu_tiên
MRR = mean(RR)
```
- Đo item đúng đầu tiên xuất hiện ở vị trí nào

### Metrics khác
- **AUC (Area Under ROC Curve)**: thường dùng cho toàn bộ ranking
- **Coverage**: % catalog items được gợi ý
- **Diversity**: độ đa dạng trong danh sách gợi ý
- **Novelty**: mức độ mới mẻ của gợi ý
- **Serendipity**: gợi ý bất ngờ nhưng thú vị

---

## 4. Evaluation Protocol

### Phân hoạch dữ liệu
**Leave-One-Out**: giữ lại interaction cuối cùng của mỗi user làm test
- Train: n-1 interactions đầu
- Test: 1 interaction cuối
- Phổ biến nhất trong các paper

**Ratio Split**: chia 80/10/10 hoặc 70/10/20 theo thời gian
- Train/Validation/Test
- Phù hợp với dữ liệu lớn

**K-Fold Cross Validation**: ít dùng cho recommender vì tốn kém

### Tập ứng viên (Candidate Generation)
**Full ranking**: so sánh với toàn bộ items user chưa tương tác
- Chuẩn xác nhất nhưng tốn kém O(|Users| × |Items|)

**Sampled ranking** (negative sampling): chọn 99 hoặc 999 items âm ngẫu nhiên + 1 item dương
- Nhanh hơn nhưng có thể bias (đã phổ biến trong nhiều benchmark)
- Một số paper mới cho thấy kết quả có thể khác với full ranking

### Lưu ý quan trọng
- Phải lọc training items ra khỏi candidate list
- Với cold-start users, cần xử lý riêng
- Seed cố định để tái tạo kết quả

---

## 5. Ba mô hình SOTA được chọn

### Model 1: LightGCN (Graph-based)
**Paper**: "LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation" (SIGIR 2020)
**Code**: https://github.com/gusye1234/LightGCN-PyTorch

**Core idea**: 
- Dùng Graph Neural Network trên user-item bipartite graph
- Loại bỏ feature transformation và activation function (không cần thiết cho CF)
- Chỉ giữ lại linear propagation: e_u^(k+1) = sum_{i∈N(u)} (1/sqrt(|N(u)||N(i)|)) * e_i^(k)
- Final embedding = trung bình cộng qua tất cả các layer

**Innovation**:
- Đơn giản hóa NGCF (tiền thân) nhưng vẫn hiệu quả hơn
- Chứng minh rằng feature transformation làm hại recommendation
- Dễ huấn luyện, ít hyperparameter

**Lý do chọn**: Baseline quan trọng nhất của graph-based CF, được cite rất nhiều

---

### Model 2: SGL (Self-supervised Graph Learning)
**Paper**: "Self-supervised Graph Learning for Recommendation" (SIGIR 2021)  
**Code**: https://github.com/wujcan/SGL-Torch

**Core idea**:
- Kết hợp self-supervised learning với GCN
- Tạo ra 2 views của graph bằng augmentation: node dropout, edge dropout, random walk
- Contrastive loss: maximize agreement giữa 2 views của cùng 1 node
- Loss = BPR loss + λ * InfoNCE contrastive loss

**Innovation**:
- Giải quyết long-tail problem: user/item ít tương tác thường bị học kém
- SSL giúp học representation tốt hơn kể cả cho sparse users/items
- Augmentation techniques for graphs

**Lý do chọn**: Đại diện cho hướng Self-supervised Learning, SOTA quan trọng

---

### Model 3: SimGCL (Simple Graph Contrastive Learning)
**Paper**: "Are Graph Augmentations Necessary? Simple Scalable Contrastive Learning for Recommendation" (SIGIR 2022)
**Code**: https://github.com/Coder-Yu/SELFRec

**Core idea**:
- Câu hỏi: Augmentation phức tạp có thực sự cần thiết?
- Thay vì augmentation trên graph structure, thêm **uniform noise** trực tiếp vào embedding space
- e' = e + Δ, Δ ~ Uniform(-ε, ε)
- Tạo 2 views bằng cách thêm 2 lần noise khác nhau → contrastive learning

**Innovation**:
- Đơn giản hơn SGL nhưng hiệu quả hơn trên nhiều benchmark
- Tránh được overhead của graph augmentation
- Dễ implement, dễ scale

**Lý do chọn**: Đại diện mới nhất, hiệu quả cao, minh chứng "simplicity wins"

---

## 6. So sánh ba mô hình

| Tiêu chí | LightGCN | SGL | SimGCL |
|---|---|---|---|
| Kiến trúc | GCN | GCN + Contrastive | GCN + Contrastive |
| Augmentation | Không | Node/Edge dropout | Noise injection |
| Training signal | BPR | BPR + InfoNCE | BPR + InfoNCE |
| Độ phức tạp | Thấp | Trung bình | Thấp-Trung bình |
| Long-tail | Trung bình | Tốt | Tốt |
| Scalability | Tốt | Trung bình | Tốt |
| Năm | 2020 | 2021 | 2022 |

---

## 7. Câu hỏi trả lời cho báo cáo

**Q: Từ khóa tìm survey?**
- "recommender systems implicit feedback survey 2022 2023 2024"
- "collaborative filtering implicit feedback review"  
- "graph neural network recommendation survey"
- Filter: SIGIR, RecSys, WWW, KDD conferences + Google Scholar sorted by citation

**Q: Tiêu chí chọn SOTA?**
1. Được cite nhiều (>100 citations)
2. Có code public và reproducible
3. Đại diện cho hướng tiếp cận khác nhau (GNN, SSL, Contrastive)
4. Kết quả tốt trên các benchmark chuẩn (MovieLens, Yelp, Amazon)
5. Publish tại top venues (SIGIR, KDD, WWW, RecSys)
