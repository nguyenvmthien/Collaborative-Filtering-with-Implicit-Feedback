# Phase 2 Last.fm Data Pipeline (Course Project)

**Báo cáo & slide Phase 2 (tiếng Việt):** xem thư mục [`reports/phase2/`](../reports/phase2/) — `PHASE2_REPORT.md`, `PHASE2_SLIDES_OUTLINE.md`, `pipeline.mmd`.


This module implements the full Phase 2 pipeline for a Last.fm collected dataset under the required scope:

- Domain: music recommendation
- User: Last.fm user
- Item: artist
- Raw interaction signal: `library.getArtists` playcount
- Model interaction: binary observed edge (`label=1`) per unique `(user, artist)`

It is designed to satisfy Phase 2 reportables and produce a model-ready dataset for Phase 3 (LightGCN/SGL style bipartite graph training).

## Important Compliance Gate

Before full crawl, complete legal/quota clearance:

1. Register one Last.fm team account and API key.
2. Contact Last.fm for academic/research usage confirmation.
3. Fill [legal_clearance.json](/c:/Users/Admin/Desktop/bigdataungdung/phase2_lastfm/docs/phase2_report_assets/legal_clearance.json) with approval details and set `"approved": true`.
4. Keep pilot crawl small until quota/rate behavior is acceptable.

The crawler enforces this gate for full-scale targets.

## Directory Contract

```
phase2_lastfm/
  README_phase2.md
  config/
    config.yaml
  data/
    seeds/
      seed_users.txt
    raw_api/
    interim/
    processed/
  logs/
  src/
    collect/
      lastfm_client.py
      crawl_network.py
      resume_state.py
    clean/
      normalize_entities.py
      build_interactions.py
      filter_kcore.py
    report/
      compute_stats.py
      make_figures.py
      export_tables.py
  docs/
    pipeline.mmd
    phase2_report_assets/
```

## Prerequisites

**API key (required):** Get a key at https://www.last.fm/api/account/create then either:

- Set env: `$env:LASTFM_API_KEY="your_api_key_here"` (PowerShell) or `export LASTFM_API_KEY=your_key` (bash)
- Or create `config/api_key.txt` with your key on a single line (copy from `config/api_key.txt.example`)

Install dependencies from repository root:

```bash
pip install -r requirements.txt
```

## CLI Contracts

Run crawler (from `phase2_lastfm/`):

```bash
# Pilot mode (target ≤ 300k, no legal clearance needed)
.\run_crawl.ps1
# Or with explicit target:
python -m src.collect.crawl_network \
  --config config/config.yaml \
  --seeds data/seeds/seed_users.txt \
  --target-raw-interactions 300000
```

For full crawl (1.3M target) set `approved: true` in `docs/phase2_report_assets/legal_clearance.json`.

Build cleaned dataset:

```bash
python -m src.clean.build_interactions \
  --config config/config.yaml \
  --raw-dir data/raw_api \
  --out-dir data/processed
```

Compute Phase 2 stats and assets:

```bash
python -m src.report.compute_stats \
  --input data/processed/interactions.csv \
  --out-dir docs/phase2_report_assets
```

## Crawl Strategy Implemented

- BFS friend-network discovery via `user.getFriends`.
- Artist-library extraction via `library.getArtists`.
- Optional timestamp enrichment is intentionally deferred (can add `user.getRecentTracks` second pass later).

## Stop Conditions

Crawler stops when any condition is met:

- raw unique `(user, artist)` edges >= requested target (`--target-raw-interactions`)
- cleaned edge estimate target reached (when configured)
- approved quota ceiling reached (bytes or request count)

## Vì sao số user ít? (Và cách tăng)

Crawler xử lý **lần lượt từng user**: với mỗi user gọi `user.getFriends` (thêm bạn vào queue) rồi `library.getArtists` **toàn bộ** thư viện (nhiều trang). Khi **tổng số cạnh (user, artist) đạt target** (ví dụ 1M) thì dừng. Vì một số user có rất nhiều artist (vài nghìn), chỉ cần **ít user** là đã đủ 1M cạnh → số user đã crawl xong thư viện (**users_library_completed**) chỉ ~156, còn **~19.839 user** vẫn nằm trong queue chưa được crawl thư viện.

**Cách có thêm user:** tăng target để crawler tiếp tục xử lý thêm user trong queue (state được lưu, chạy lại sẽ resume). Ví dụ:

```bash
python -m src.collect.crawl_network --config config/config.yaml --seeds data/seeds/seed_users.txt --target-raw-interactions 2500000
```

Target 2.5M sẽ crawl thêm nhiều user → sau k-core có thể được vài trăm đến vài nghìn user (tùy phân bố).

## Processing Rules Implemented

- Deterministic entity normalization and ID mapping.
- MBID preferred for artist identity, normalized artist name fallback.
- Deduplicate by `(user_id, item_id)`.
- Binary `label=1` for each observed edge.
- Keep `playcount` as metadata.
- Iterative filtering to stable k-core with:
  - `min_user_interactions >= 10`
  - `min_item_interactions >= 5`

## Output Files

Main processed outputs in `data/processed/`:

- `interactions.csv`
- `users.csv`
- `items.csv`
- `interactions_binary.tsv`
- `manifest.json`

Audit output in `data/interim/`:

- `audit_interactions.csv`

## Reproducibility

The pipeline is:

- idempotent
- resumable
- config-driven
- deterministic for entity mapping

Every API call is logged with status and bytes. Every output file is included in a manifest with checksums.
