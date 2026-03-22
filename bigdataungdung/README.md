# CSC14114 - Recommendation System with Implicit Feedback

Đồ án môn Ứng dụng Dữ liệu Lớn - HCMUS

## Tổng quan

Xây dựng và so sánh 3 mô hình SOTA cho Recommender Systems với Implicit Feedback:
- **LightGCN** (SIGIR 2020) - Graph-based Collaborative Filtering
- **SGL** (SIGIR 2021) - Self-supervised Graph Learning
- **SimGCL** (SIGIR 2022) - Simple Graph Contrastive Learning

Thực nghiệm trên 5 datasets: MovieLens-1M, Yelp2018, Amazon-Book, Gowalla, Steam (tự thu thập)

## Cấu trúc project

```
bigdataungdung/
├── phase1_research/
│   └── RESEARCH_NOTES.md          # Lý thuyết, câu hỏi trả lời
│
├── phase2_dataset/
│   ├── scripts/
│   │   ├── collect_steam.py                   # Thu thập Steam data
│   │   ├── preprocess.py                      # Tiền xử lý data
│   │   └── download_standard_datasets.py      # Tải 4 datasets chuẩn
│   ├── raw/                                   # Raw data (chưa xử lý)
│   └── processed/                             # Data đã xử lý
│
├── phase2_lastfm/                             # Dataset tự thu thập Last.fm (≥1M interactions)
│   └── README_phase2.md                     # Pipeline + link reports/phase2
│
├── phase3_experiments/
│   ├── models/
│   │   ├── lightgcn.py            # LightGCN implementation
│   │   ├── sgl.py                 # SGL implementation
│   │   ├── simgcl.py              # SimGCL implementation
│   │   └── metrics.py             # Evaluation metrics
│   ├── datasets/                  # Symlink/copy của processed data
│   ├── results/                   # Kết quả experiments
│   ├── notebooks/
│   │   └── analysis.ipynb         # Phân tích và visualization
│   └── run_experiment.py          # Script chạy experiments
│
├── reports/
│   ├── phase1/                    # Báo cáo giai đoạn 1
│   ├── phase2/                    # Báo cáo giai đoạn 2
│   └── phase3/                    # Final report
│
└── requirements.txt
```

## Cài đặt

```bash
pip install -r requirements.txt
```

## Hướng dẫn theo từng giai đoạn

### Giai đoạn 1: Nghiên cứu (30%)

Đọc file `phase1_research/RESEARCH_NOTES.md` để hiểu:
- Implicit vs Explicit feedback
- Evaluation metrics (Precision@K, Recall@K, NDCG@K, HR@K, MRR@K, MAP@K)
- Ba mô hình SOTA: LightGCN, SGL, SimGCL

**Output**: Báo cáo + slide trình bày 20 phút

---

### Giai đoạn 2: Thu thập dữ liệu (30%)

**Bước 1: Tải 4 datasets chuẩn**
```bash
cd phase2_dataset/scripts
python download_standard_datasets.py --dataset ml-1m
python download_standard_datasets.py --dataset gowalla
# Yelp2018 và Amazon-Book: xem hướng dẫn trong script
```

**Bước 2: Thu thập Steam dataset (≥1M interactions)**
```bash
# Option A: Tải dataset UCSD Steam có sẵn (Khuyến nghị)
# wget https://cseweb.ucsd.edu/~jmcauley/datasets/steam/australian_users_items.json.gz

# Option B: Thu thập qua Steam API
python collect_steam.py
```

**Bước 3: Tiền xử lý**
```bash
python preprocess.py --input ../raw/steam_raw.csv --output ../processed/ --k_core 10
```

---

### Giai đoạn 3: Thực nghiệm (40%)

**Bước 1: Copy datasets vào thư mục experiments**
```bash
# Copy processed datasets vào phase3_experiments/datasets/
# Hoặc tạo symlink
```

**Bước 2: Chạy experiments**
```bash
cd phase3_experiments

# Chạy 1 experiment
python run_experiment.py --model lightgcn --dataset ml-1m --runs 3

# Chạy tất cả 15 experiments (MẤT NHIỀU THỜI GIAN!)
python run_experiment.py --all --runs 3

# Dùng GPU nếu có
python run_experiment.py --all --runs 3 --device cuda
```

**Bước 3: Phân tích kết quả**
```bash
jupyter notebook phase3_experiments/notebooks/analysis.ipynb
```

---

## Lịch thực hiện đề xuất

| Tuần | Việc cần làm |
|------|-------------|
| 1 | Đọc 3 papers, hiểu lý thuyết, viết báo cáo Phase 1 |
| 2 | Trình bày Phase 1 + bắt đầu thu thập dữ liệu |
| 3 | Thu thập Steam data, tải 4 datasets chuẩn, xử lý |
| 4 | Trình bày Phase 2 + bắt đầu implement models |
| 5 | Chạy experiments (15 experiments × 3-5 runs) |
| 6 | Phân tích kết quả, viết báo cáo cuối |
| 7 | Hoàn thiện báo cáo, chuẩn bị slide, trình bày final |

## Lưu ý quan trọng

- Chạy mỗi experiment 3-5 lần với seeds khác nhau
- Ghi lại thời gian training và tài nguyên sử dụng
- Dataset Steam tự thu thập cần ≥ 1,000,000 interactions
- Evaluation protocol: Leave-one-out split + Full ranking
- Metric chính: NDCG@20, Recall@20
