# CSC14114 - Recommendation System with Implicit Feedback

Course Project — Big Data Applications, HCMUS

Participant: Nguyễn Văn Minh Thiện, Đặng Văn Kỳ.

## Overview

This project builds and compares three SOTA models for Recommender Systems with Implicit Feedback:

- **LightGCN** (SIGIR 2020) — Graph-based Collaborative Filtering
- **SGL** (SIGIR 2021) — Self-supervised Graph Learning
- **SimGCL** (SIGIR 2022) — Simple Graph Contrastive Learning

Experiments are conducted on a self-collected **Last.fm** dataset (~1M interactions) and **MovieLens-1M**.

## Project Structure

```
bigdata_application_project/
├── phase1_research/
│   └── RESEARCH_NOTES.md              # Theory: implicit feedback, metrics, 3 models
│
├── phase2_lastfm/                     # Last.fm data collection and processing
│   ├── README_phase2.md               # Phase 2 pipeline guide
│   ├── config/
│   │   └── config.yaml
│   ├── src/
│   │   ├── collect/                   # BFS friend-network crawler + library.getArtists
│   │   ├── clean/                     # Entity normalization, k-core filtering
│   │   └── report/                    # Stats computation, table export
│   ├── docs/
│   │   └── phase2_report_assets/      # Figures, stats tables
│   ├── logs/
│   ├── results/
│   ├── run_crawl.ps1
│   └── lastfm_phase2_processed.zip    # Pre-processed dataset
│
├── phase3/                            # Model experiments
│   ├── code/
│   │   ├── Phase3_Part1_LightGCN.ipynb
│   │   ├── Phase3_Part2_SGL.ipynb
│   │   ├── Phase3_Part3_SimGCL.ipynb
│   │   └── analyze_results.ipynb
│   ├── results/
│   │   └── results.csv                # All experiment results
│   └── report/                        # Phase 3 report assets
│
├── BigData_RecSys_Colab.ipynb         # Google Colab notebook
├── requirements.txt
└── README.md
```

## Installation

```bash
pip install -r requirements.txt
```

## Phase 1: Research

See `phase1_research/RESEARCH_NOTES.md` for:
- Implicit vs Explicit feedback
- Evaluation metrics: Precision@K, Recall@K, NDCG@K, HR@K, MRR@K
- Model theory: LightGCN, SGL, SimGCL

## Phase 2: Data Collection (Last.fm)

**Requirement:** API key from [last.fm/api/account/create](https://www.last.fm/api/account/create)

```bash
# Set API key
export LASTFM_API_KEY=your_api_key        # bash
$env:LASTFM_API_KEY="your_api_key"        # PowerShell

cd phase2_lastfm

# Pilot crawl (≤300k interactions, no legal clearance needed)
python -m src.collect.crawl_network \
  --config config/config.yaml \
  --seeds data/seeds/seed_users.txt \
  --target-raw-interactions 300000

# Full crawl (≥1M): set "approved": true in docs/phase2_report_assets/legal_clearance.json
.\run_crawl.ps1

# Build cleaned dataset
python -m src.clean.build_interactions \
  --config config/config.yaml \
  --raw-dir data/raw_api \
  --out-dir data/processed

# Compute stats
python -m src.report.compute_stats \
  --input data/processed/interactions.csv \
  --out-dir docs/phase2_report_assets
```

A pre-processed dataset is available at `phase2_lastfm/lastfm_phase2_processed.zip`.

## Phase 3: Experiments

Run the notebooks in `phase3/code/` in order:

1. `Phase3_Part1_LightGCN.ipynb`
2. `Phase3_Part2_SGL.ipynb`
3. `Phase3_Part3_SimGCL.ipynb`
4. `analyze_results.ipynb` — aggregate and compare results

Alternatively, use `BigData_RecSys_Colab.ipynb` to run on Google Colab.

Results (NDCG@20, Recall@20, Precision@20, HR@20, MRR@20) are saved to `phase3/results/results.csv`.

## Results

**Primary metrics:** NDCG@20, Recall@20  
**Evaluation protocol:** Leave-one-out split + Full ranking  
Each experiment is run 3 times with different random seeds.

See `phase3/results/results.csv` and `phase3/report/` for full details.
