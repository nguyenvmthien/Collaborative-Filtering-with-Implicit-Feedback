import argparse
import copy
import json
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import torch
import torch.nn as nn
import torch.nn.functional as F


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


def resolve_device(device_name):
    if device_name == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        return "cpu"
    return device_name


def resolve_dataset_dir(dataset_dir):
    dataset_dir = Path(dataset_dir)
    if dataset_dir.exists():
        return dataset_dir.resolve()
    raise FileNotFoundError(dataset_dir)


def load_dataset(dataset_dir):
    required = ["train.csv", "val.csv", "test.csv", "info.json"]
    for name in required:
        if not (dataset_dir / name).exists():
            raise FileNotFoundError(f"Missing file: {dataset_dir / name}")

    with (dataset_dir / "info.json").open("r", encoding="utf-8") as handle:
        info = json.load(handle)

    train_df = pd.read_csv(dataset_dir / "train.csv")
    val_df = pd.read_csv(dataset_dir / "val.csv")
    test_df = pd.read_csv(dataset_dir / "test.csv")
    return train_df, val_df, test_df, info


class LightGCN(nn.Module):
    def __init__(self, n_users, n_items, embedding_dim=64, n_layers=3, reg_weight=1e-4, device="cpu"):
        super().__init__()
        self.n_users = int(n_users)
        self.n_items = int(n_items)
        self.embedding_dim = int(embedding_dim)
        self.n_layers = int(n_layers)
        self.reg_weight = float(reg_weight)
        self.device = device

        self.user_embedding = nn.Embedding(self.n_users, self.embedding_dim)
        self.item_embedding = nn.Embedding(self.n_items, self.embedding_dim)
        nn.init.xavier_uniform_(self.user_embedding.weight)
        nn.init.xavier_uniform_(self.item_embedding.weight)
        self.norm_adj = None

    def set_graph(self, train_user_ids, train_item_ids):
        n_nodes = self.n_users + self.n_items
        rows = np.concatenate([train_user_ids, train_item_ids + self.n_users])
        cols = np.concatenate([train_item_ids + self.n_users, train_user_ids])
        data = np.ones(len(rows), dtype=np.float32)

        adj = sp.csr_matrix((data, (rows, cols)), shape=(n_nodes, n_nodes), dtype=np.float32)
        degree = np.asarray(adj.sum(axis=1)).reshape(-1)
        d_inv_sqrt = np.power(degree, -0.5, where=degree > 0)
        d_inv_sqrt[~np.isfinite(d_inv_sqrt)] = 0.0
        norm = sp.diags(d_inv_sqrt) @ adj @ sp.diags(d_inv_sqrt)
        norm = norm.tocoo()

        indices = np.vstack((norm.row, norm.col)).astype(np.int64)
        values = norm.data.astype(np.float32)
        self.norm_adj = torch.sparse_coo_tensor(
            indices=torch.from_numpy(indices),
            values=torch.from_numpy(values),
            size=(n_nodes, n_nodes),
            device=self.device,
        ).coalesce()

        print(f"Graph built: {n_nodes} nodes, {len(values)} edges")

    def forward(self):
        all_embeddings = torch.cat([self.user_embedding.weight, self.item_embedding.weight], dim=0)
        layer_embeddings = [all_embeddings]

        for _ in range(self.n_layers):
            all_embeddings = torch.sparse.mm(self.norm_adj, all_embeddings)
            layer_embeddings.append(all_embeddings)

        final_embeddings = torch.stack(layer_embeddings, dim=1).mean(dim=1)
        user_embeddings = final_embeddings[: self.n_users]
        item_embeddings = final_embeddings[self.n_users :]
        return user_embeddings, item_embeddings

    def bpr_loss(self, user_ids, pos_item_ids, neg_item_ids):
        user_emb, item_emb = self.forward()
        u_emb = user_emb[user_ids]
        p_emb = item_emb[pos_item_ids]
        n_emb = item_emb[neg_item_ids]

        pos_scores = (u_emb * p_emb).sum(dim=-1)
        neg_scores = (u_emb * n_emb).sum(dim=-1)
        bpr = -F.logsigmoid(pos_scores - neg_scores).mean()

        reg = self.reg_weight * (
            self.user_embedding.weight[user_ids].norm(2).pow(2)
            + self.item_embedding.weight[pos_item_ids].norm(2).pow(2)
            + self.item_embedding.weight[neg_item_ids].norm(2).pow(2)
        ) / len(user_ids)

        return bpr + reg

    def get_user_rating(self, user_ids):
        user_emb, item_emb = self.forward()
        return torch.matmul(user_emb[user_ids], item_emb.T)

    @torch.no_grad()
    def predict_topk(self, user_ids, k=20, exclude_interactions=None):
        self.eval()
        user_tensor = torch.LongTensor(user_ids).to(self.device)
        scores = self.get_user_rating(user_tensor)

        if exclude_interactions:
            for i, uid in enumerate(user_ids):
                seen = exclude_interactions.get(uid, set())
                if seen:
                    scores[i, list(seen)] = float("-inf")

        _, topk_items = scores.topk(k, dim=-1)
        return topk_items.cpu().numpy()


def precision_at_k(recommended, relevant, k):
    rec_k = recommended[:k]
    rel = set(relevant)
    hits = sum(1 for item in rec_k if item in rel)
    return hits / k


def recall_at_k(recommended, relevant, k):
    if not relevant:
        return 0.0
    rec_k = recommended[:k]
    rel = set(relevant)
    hits = sum(1 for item in rec_k if item in rel)
    return hits / len(rel)


def hit_rate_at_k(recommended, relevant, k):
    return 1.0 if set(recommended[:k]) & set(relevant) else 0.0


def ndcg_at_k(recommended, relevant, k):
    rec_k = recommended[:k]
    rel = set(relevant)

    dcg = 0.0
    for i, item in enumerate(rec_k):
        if item in rel:
            dcg += 1.0 / np.log2(i + 2)

    n_rel = min(len(rel), k)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(n_rel))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def mrr_at_k(recommended, relevant, k):
    rel = set(relevant)
    for i, item in enumerate(recommended[:k]):
        if item in rel:
            return 1.0 / (i + 1)
    return 0.0


def average_precision_at_k(recommended, relevant, k):
    rel = set(relevant)
    if not rel:
        return 0.0

    hits = 0
    sum_precision = 0.0
    for i, item in enumerate(recommended[:k]):
        if item in rel:
            hits += 1
            sum_precision += hits / (i + 1)

    return sum_precision / min(len(rel), k)


def evaluate_user(recommended, relevant, k_list):
    out = {}
    for k in k_list:
        out[f"precision@{k}"] = precision_at_k(recommended, relevant, k)
        out[f"recall@{k}"] = recall_at_k(recommended, relevant, k)
        out[f"ndcg@{k}"] = ndcg_at_k(recommended, relevant, k)
        out[f"hr@{k}"] = hit_rate_at_k(recommended, relevant, k)
        out[f"mrr@{k}"] = mrr_at_k(recommended, relevant, k)
        out[f"map@{k}"] = average_precision_at_k(recommended, relevant, k)
    return out


@torch.no_grad()
def evaluate_model(model, test_data, train_interactions, k_list, batch_size=512):
    max_k = max(k_list)

    test_dict = {}
    for _, row in test_data.iterrows():
        uid = int(row["user_idx"])
        iid = int(row["item_idx"])
        test_dict.setdefault(uid, []).append(iid)

    users = list(test_dict.keys())
    all_metrics = {
        f"{metric}@{k}": []
        for k in k_list
        for metric in ["precision", "recall", "ndcg", "hr", "mrr", "map"]
    }

    for i in range(0, len(users), batch_size):
        batch_users = users[i : i + batch_size]
        batch_topk = model.predict_topk(batch_users, k=max_k, exclude_interactions=train_interactions)

        for j, uid in enumerate(batch_users):
            rec = batch_topk[j].tolist()
            rel = test_dict[uid]
            user_metrics = evaluate_user(rec, rel, k_list)
            for key, val in user_metrics.items():
                all_metrics[key].append(val)

    return {key: float(np.mean(vals)) if vals else 0.0 for key, vals in all_metrics.items()}


def format_results(metrics, dataset, model_name):
    lines = [f"\n{'=' * 60}"]
    lines.append(f"  Model: {model_name} | Dataset: {dataset}")
    lines.append(f"{'=' * 60}")

    k_values = sorted({int(key.split("@")[1]) for key in metrics.keys()})
    for k in k_values:
        lines.append(f"\n  @K={k}:")
        for metric in ["precision", "recall", "ndcg", "hr", "mrr", "map"]:
            key = f"{metric}@{k}"
            lines.append(f"    {key:15s}: {metrics[key]:.4f}")

    lines.append(f"{'=' * 60}")
    return "\n".join(lines)


def build_train_interactions(train_df):
    interactions = {}
    for _, row in train_df.iterrows():
        uid = int(row["user_idx"])
        iid = int(row["item_idx"])
        interactions.setdefault(uid, set()).add(iid)
    return interactions


def negative_sampling(user_id, n_items, train_interactions):
    seen = train_interactions.get(user_id, set())
    while True:
        neg = random.randint(0, n_items - 1)
        if neg not in seen:
            return neg


def train_epoch(model, train_df, train_interactions, n_items, optimizer, batch_size, device):
    model.train()
    users = train_df["user_idx"].to_numpy()
    pos_items = train_df["item_idx"].to_numpy()
    order = np.random.permutation(len(users))
    users = users[order]
    pos_items = pos_items[order]

    losses = []
    for start in range(0, len(users), batch_size):
        end = min(start + batch_size, len(users))
        batch_users = users[start:end]
        batch_pos = pos_items[start:end]
        batch_neg = np.array([negative_sampling(int(u), n_items, train_interactions) for u in batch_users])

        u = torch.LongTensor(batch_users).to(device)
        p = torch.LongTensor(batch_pos).to(device)
        n = torch.LongTensor(batch_neg).to(device)

        optimizer.zero_grad()
        loss = model.bpr_loss(u, p, n)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())

    return float(np.mean(losses))


def main():
    parser = argparse.ArgumentParser(description="Run LightGCN on a small processed dataset")
    parser.add_argument("--dataset-dir", type=Path, default=Path("demo/data/steam_tiny"))
    parser.add_argument("--device", default="auto", help="auto, cpu, or cuda")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--embedding-dim", type=int, default=64)
    parser.add_argument("--n-layers", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--reg-weight", type=float, default=1e-4)
    parser.add_argument("--eval-every", type=int, default=1)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--k-list", default="10,20")
    args = parser.parse_args()

    dataset_dir = resolve_dataset_dir(args.dataset_dir)
    device = resolve_device(args.device)
    k_list = [int(x) for x in args.k_list.split(",") if x.strip()]

    set_seed(args.seed)
    train_df, val_df, test_df, info = load_dataset(dataset_dir)
    train_interactions = build_train_interactions(train_df)

    model = LightGCN(
        n_users=info["n_users"],
        n_items=info["n_items"],
        embedding_dim=args.embedding_dim,
        n_layers=args.n_layers,
        reg_weight=args.reg_weight,
        device=device,
    ).to(device)
    model.set_graph(train_df["user_idx"].to_numpy(), train_df["item_idx"].to_numpy())
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    best_state = copy.deepcopy(model.state_dict())
    best_epoch = 0
    best_score = float("-inf")
    patience_left = args.patience
    target_metric = f"ndcg@{max(k_list)}"

    print(f"Dataset: {info['dataset']} from {dataset_dir}")
    print(
        f"Users={info['n_users']}, Items={info['n_items']}, "
        f"Train={len(train_df)}, Val={len(val_df)}, Test={len(test_df)}"
    )
    print(f"Device: {device}")

    start_time = time.time()
    for epoch in range(1, args.epochs + 1):
        loss = train_epoch(
            model=model,
            train_df=train_df,
            train_interactions=train_interactions,
            n_items=info["n_items"],
            optimizer=optimizer,
            batch_size=args.batch_size,
            device=device,
        )
        print(f"Epoch {epoch:03d} | loss={loss:.4f}")

        if epoch % args.eval_every != 0:
            continue

        val_metrics = evaluate_model(model, val_df, train_interactions, k_list=k_list)
        score = val_metrics[target_metric]
        print(f"Validation {target_metric}={score:.4f}")

        if score > best_score:
            best_score = score
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            patience_left = args.patience
        else:
            patience_left -= 1
            if patience_left <= 0:
                print("Early stopping triggered")
                break

    model.load_state_dict(best_state)
    elapsed = time.time() - start_time

    test_metrics = evaluate_model(model, test_df, train_interactions, k_list=k_list)
    print(format_results(test_metrics, info.get("dataset", dataset_dir.name), "lightgcn-demo"))
    print(f"Best epoch: {best_epoch}")
    print(f"Elapsed time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
