"""Materialize the public Horizon RuBQ pilot outside the source checkout."""
# /// script
# requires-python = ">=3.12"
# dependencies = ["pandas==3.0.5", "numpy==2.5.2", "pyarrow==26.0.1", "huggingface-hub==2.4.0"]
# ///
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

DATASET = "mteb/RuBQReranking"
REVISION = "f2eac2f1f82445938af650c2a285a34dd77a16eb"
SAMPLE_SHA256 = "a3367f45b2650312358745c67931d004eae78233d379e570e0339719baf2b6b5"


def load_part(name, dataset_dir):
    filename = f"{name}/test-00000-of-00001.parquet"
    path = dataset_dir / filename if dataset_dir else hf_hub_download(
        DATASET, filename, repo_type="dataset", revision=REVISION
    )
    return pd.read_parquet(path)


def materialize(dataset_dir):
    queries = load_part("queries", dataset_dir).set_index("_id")["text"]
    corpus = load_part("corpus", dataset_dir).set_index("_id")
    documents = (corpus["title"].fillna("") + " " + corpus["text"]).str.strip().str[:2000]
    labels = load_part("data", dataset_dir).set_index(["query-id", "corpus-id"])["score"].to_dict()
    lists = load_part("top_ranked", dataset_dir)
    lists = lists[lists["query-id"].isin(queries.index)].sample(frac=1.0, random_state=0)
    rows = []
    for qid, candidates in lists[["query-id", "corpus-ids"]].itertuples(index=False, name=None):
        cids = [cid for cid in candidates if cid in documents.index]
        rels = [int(labels.get((qid, cid), 0)) for cid in cids]
        if not (0 < sum(r > 0 for r in rels) < len(cids)):
            continue
        rows.append((qid, queries.at[qid], documents.loc[cids].tolist(), rels, cids))
        if len(rows) == 150:
            break
    frame = pd.DataFrame(rows, columns=["qid", "query", "docs", "rels", "cids"])
    payload = json.dumps(frame.to_dict("records"), ensure_ascii=False, separators=(",", ":")).encode()
    if hashlib.sha256(payload).hexdigest() != SAMPLE_SHA256:
        raise ValueError("Sample differs from the published 150-query pilot")
    return frame


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Output Parquet path")
    parser.add_argument("--dataset-dir", type=Path, help="Optional local checkout of the pinned dataset")
    args = parser.parse_args()
    sample = materialize(args.dataset_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sample.to_parquet(args.output, index=False)
    print(f"Wrote {len(sample)} queries and 3,656 pairs to {args.output}")
