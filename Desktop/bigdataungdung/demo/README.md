# LightGCN Demo (Self-Contained)

Everything in this folder is standalone.
No import from `phase2_dataset` or `phase3_experiments`.

## Colab Minimal Setup

If you uploaded only these files to `/content`:

- `download_movielens_demo.py`
- `run_lightgcn_demo.py`
- optional `data/steam_tiny/` dataset

Install packages:

```bash
!pip install torch pandas numpy scipy requests
```

## Option A: Download Small MovieLens Dataset

```bash
!python download_movielens_demo.py --output-dir data --dataset-name ml100k_tiny
!python run_lightgcn_demo.py --dataset-dir data/ml100k_tiny --epochs 10
```

## Option B: Use Included `steam_tiny` Dataset

If your tiny dataset folder is at `/content/data/steam_tiny`:

```bash
!python run_lightgcn_demo.py --dataset-dir data/steam_tiny --epochs 10
```

If your tiny dataset folder is at `/content/demo/data/steam_tiny`:

```bash
!python run_lightgcn_demo.py --dataset-dir demo/data/steam_tiny --epochs 10
```

## Expected Dataset Format

`--dataset-dir` must contain:

- `train.csv` with columns `user_idx,item_idx`
- `val.csv` with columns `user_idx,item_idx`
- `test.csv` with columns `user_idx,item_idx`
- `info.json` with `n_users` and `n_items`
