#!/usr/bin/env python3
"""Check and summarize RuBQ score traces and latency measurements."""

import argparse
from collections import Counter
from itertools import combinations
import json
import math
from pathlib import Path
import re
import statistics

import numpy as np

from run_rubq import COUNTS, LIMIT, MODELS, expected_model_sha256, load_sample, require, sha256, write_json


LABELS = {
    "yuanbao-f16": "Yuanbao F16", "yuanbao-q8": "Yuanbao Q8_0",
    "yuanbao-q4": "Yuanbao Q4_K_M", "qwen-q8": "Qwen Q8_0 (ggml-org)",
    "pilot-bf16": "Yuanbao BF16 (earlier MPS pilot)",
}
KEYS = ("qid", "cid", "label")


def load_jsonl(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream]


def order(rows, tie):
    return sorted(rows, key=lambda row: (-row["score"], tie * row["label"]))


def metrics(ranked, ideal):
    discounted = sum((2 ** row["label"] - 1) / math.log2(i + 2) for i, row in enumerate(ranked[:10]))
    reciprocal_rank = next((1 / (i + 1) for i, row in enumerate(ranked[:10]) if row["label"] > 0), 0.0)
    return {"ndcg_at_10": discounted / ideal, "mrr_at_10": reciprocal_rank}


def evaluate(trace, sample):
    expected = [(q["qid"], cid, label) for q in sample
                for cid, label in zip(q["cids"], q["rels"], strict=True)]
    observed = [tuple(row[key] for key in KEYS) for row in trace]
    require(observed == expected, "Trace contains missing, extra or reordered candidates")
    require(all(math.isfinite(row["score"]) and 0 <= row["score"] <= 1 for row in trace),
            "Trace contains invalid probability scores")
    require(all(0 < row["input_tokens"] <= LIMIT for row in trace), "Invalid prompt length")
    offset = 0
    by_query = {}
    for query in sample:
        size = len(query["cids"])
        rows = trace[offset:offset + size]
        labels = sorted(query["rels"], reverse=True)
        ideal = sum((2 ** label - 1) / math.log2(i + 2) for i, label in enumerate(labels[:10]))
        variants = {
            policy: metrics(order(rows, tie), ideal)
            for policy, tie in (("stable", 0), ("nonrelevant_first", 1), ("relevant_first", -1))
        }
        top = order(rows, 0)[0]
        different_labels = any(rels > 1 for rels in (
            len({row["label"] for row in rows if row["score"] == score})
            for score, count in Counter(row["score"] for row in rows).items() if count > 1
        ))
        by_query[query["qid"]] = {
            "metrics": variants, "top1": top["cid"], "top1_label": top["label"],
            "ties": size > len({row["score"] for row in rows}),
            "top1_tied": sum(row["score"] == top["score"] for row in rows) > 1,
            "mixed_label_tie": different_labels,
        }
        offset += size
    summary = {
        "queries": len(by_query), "pairs": offset,
        "ties": {key: sum(row[key] for row in by_query.values())
                 for key in ("ties", "top1_tied", "mixed_label_tie")},
        "top1_relevant": sum(row["top1_label"] > 0 for row in by_query.values()),
        "metrics": {
            policy: {name: statistics.mean(item["metrics"][policy][name] for item in by_query.values())
                     for name in ("ndcg_at_10", "mrr_at_10")}
            for policy in ("stable", "nonrelevant_first", "relevant_first")
        },
        "score": {operation: function(row["score"] for row in trace)
                  for operation, function in (("minimum", min), ("median", statistics.median), ("maximum", max))},
    }
    summary["score"].update(zeros=sum(row["score"] == 0 for row in trace),
                            ones=sum(row["score"] == 1 for row in trace))
    return summary, by_query


def input_audit(trace, query_counts):
    totals = Counter()
    for row in trace:
        totals[row["qid"]] += row["input_tokens"]
    require(list(totals.items()) == [(q["qid"], q["prompt_tokens"]) for q in query_counts],
            "Request token totals do not reconcile with candidate trace")
    fallback = [row for row in trace if not row["target_exact"]]
    return {
        "min": min(row["input_tokens"] for row in trace),
        "median": statistics.median(row["input_tokens"] for row in trace),
        "max": max(row["input_tokens"] for row in trace),
        "total": sum(totals.values()),
        "target_truncated": sum(row["target_truncated"] for row in trace),
        "effective_512": sum(row["input_tokens"] == LIMIT for row in trace),
        "target_exact": len(trace) - len(fallback),
        "fallback_untruncated": sum(not row["target_truncated"] for row in fallback),
        "fallback_token_delta_counts": dict(sorted(Counter(row["target_token_delta"] for row in fallback).items())),
        "fallback_utf8_bytes_dropped": sum(row["utf8_tail_bytes"] for row in fallback),
        "fallback_max_utf8_bytes_dropped": max((row["utf8_tail_bytes"] for row in fallback), default=0),
        "fallback_extra_trim_bytes": sum(row["extra_trim_bytes"] for row in fallback),
    }


def compare(base, candidate, traces, queries):
    x = [row["score"] for row in traces[base]]
    y = [row["score"] for row in traces[candidate]]
    errors = sorted(abs(a - b) for a, b in zip(x, y, strict=True))
    changes = Counter()
    for qid, first in queries[base].items():
        second = queries[candidate][qid]
        changes["changed_document"] += first["top1"] != second["top1"]
        changes["became_relevant"] += first["top1_label"] <= 0 < second["top1_label"]
        changes["became_nonrelevant"] += second["top1_label"] <= 0 < first["top1_label"]
    return {
        "base": base, "candidate": candidate, "top1": dict(changes),
        "score_pearson": statistics.correlation(x, y), "score_mae": statistics.mean(errors),
        "score_rmse": math.sqrt(statistics.mean(e * e for e in errors)),
        "score_abs_p95": errors[math.ceil(0.95 * len(errors)) - 1], "score_max_abs": errors[-1],
    }


def paired_bootstrap(queries):
    names = ("ndcg_at_10", "mrr_at_10")
    qwen = queries["qwen-q8"]
    yuanbao = queries["yuanbao-q8"]
    differences = np.asarray([
        [yuanbao[qid]["metrics"]["stable"][name] - row["metrics"]["stable"][name] for name in names]
        for qid, row in qwen.items()
    ])
    draws, seed = 10_000, 0
    rng = np.random.Generator(np.random.PCG64(seed))
    indices = rng.integers(len(differences), size=(draws, len(differences)))
    means = differences[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975], axis=0, method="linear")
    return {
        "comparison": "Yuanbao Q8_0 minus shipped Qwen Q8_0", "query_count": len(differences),
        "draws": draws, "seed": seed, "generator": "NumPy PCG64", "numpy_version": np.__version__,
        "method": "Linear percentile interval from paired query resampling with replacement",
        "metrics": {
            name: {"difference": float(delta), "lower_95": float(lower), "upper_95": float(upper)}
            for name, delta, lower, upper in zip(names, differences.mean(axis=0), low, high, strict=True)
        },
    }


def summarize_latency(raw):
    cold = raw["cold"]
    warm = {}
    for count in COUNTS:
        row = raw["warm"][str(count)]
        samples = sorted(row["samples_ms"])
        lengths = row["input_tokens"]
        require(len(lengths) == count and max(lengths) <= LIMIT and len(samples), "Invalid timing sample")
        require(row["median_ms"] == statistics.median(samples)
                and row["p95_ms"] == samples[math.ceil(len(samples) * 0.95) - 1],
                "Invalid warmed latency reduction")
        warm[str(count)] = {
            "repeats": len(samples), "warmups": row["warmups"],
            "median_ms": row["median_ms"], "p95_ms": row["p95_ms"],
            "total_input_tokens": sum(lengths), "min_pair_tokens": min(lengths),
            "median_pair_tokens": statistics.median(lengths), "max_pair_tokens": max(lengths),
            "min_document_characters": min(row["document_characters"]),
            "max_document_characters": max(row["document_characters"]),
        }
    return {
        "started_utc": raw["started_utc"], "finished_utc": raw["finished_utc"],
        "cold_repeats": len(cold), "ready_ms": statistics.median(r["ready_ms"] for r in cold),
        "first_25_ms": statistics.median(r["first_25_ms"] for r in cold),
        "max_rss_bytes": max(r["maximum_resident_set_size_bytes"] for r in cold),
        "max_peak_footprint_bytes": max(r["peak_memory_footprint_bytes"] for r in cold),
        "warm": warm,
    }


def verify_server_log(path, filename, port):
    log = path.read_text()
    model = re.search(r"loading model '(.*)'$", log, re.MULTILINE)
    listener = re.search(r"listening on http://127\.0\.0\.1:(\d+)$", log, re.MULTILINE)
    require(model and Path(model[1]).name == filename and listener and int(listener[1]) == port,
            f"Wrong model or port in {path}")
    offload = re.search(r"offloaded (\d+)/(\d+) layers to GPU", log)
    slot = re.search(r"n_slots = (\d+), n_ctx_slot = (\d+)", log)
    require(offload and offload[1] == offload[2] and slot and "MTL0" in log
            and re.search(r"flash_attn\s*= enabled", log), f"Missing Metal runtime evidence in {path}")
    cached = re.findall(r"cached n_tokens = (\d+)", log)
    require(cached and set(cached) == {"0"}, f"Unexpected prompt caching in {path}")
    return {"layers_offloaded": int(offload[1]), "slots": int(slot[1]),
            "context_tokens_per_slot": int(slot[2])}


def markdown(report):
    models = report["models"]
    timing = report["latency"]
    common = report["runtime"]
    text = [
        "---", "type: Benchmark Report",
        "description: RuBQ pilot ranking, exact-tie sensitivity, and Apple Metal performance for the four GGUFs.",
        f'created: "{report["date"]}"', "---", "",
        "# RuBQ pilot on llama.cpp Metal", "",
        f'The same {report["sample"]["queries"]} Russian queries, {report["sample"]["pairs"]:,} candidate pairs '
        f'and {report["sample"]["positive_labels"]} positive labels were scored by each GGUF.',
        "This pilot measures reranking on preselected candidates from RuBQ.", "",
        "| Model | nDCG@10 | MRR@10 | Relevant top 1 | Top 1 changes vs F16 | GGUF MiB |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    f16_comparisons = {c["candidate"]: c for c in report["comparisons"] if c["base"] == "yuanbao-f16"}
    for name, result in models.items():
        stable = result["metrics"]["stable"]
        changes = f16_comparisons.get(name, {}).get("top1", {}).get("changed_document", "—")
        size = f'{result["file"]["size_bytes"] / 2**20:.1f}' if "file" in result else "—"
        text.append(f'| {LABELS[name]} | {stable["ndcg_at_10"]:.4f} | {stable["mrr_at_10"]:.4f} | '
                    f'{result["top1_relevant"]} | {changes} | {size} |')
    bootstrap = report["paired_bootstrap"]
    intervals = bootstrap["metrics"]
    ndcg, mrr = intervals["ndcg_at_10"], intervals["mrr_at_10"]
    text += [
        "",
        f'Yuanbao Q8_0 improved mean nDCG@10 by {ndcg["difference"]:+.4f} '
        f'(95% CI {ndcg["lower_95"]:+.4f} to {ndcg["upper_95"]:+.4f}) and mean MRR@10 by '
        f'{mrr["difference"]:+.4f} (95% CI {mrr["lower_95"]:+.4f} to {mrr["upper_95"]:+.4f}) '
        "relative to shipped Qwen Q8_0.",
        f'The paired percentile bootstrap used {bootstrap["draws"]:,} draws of the '
        f'{bootstrap["query_count"]} queries with replacement, seed `{bootstrap["seed"]}` '
        f'({bootstrap["generator"]}), and the same draws for both metrics.',
        "", "## Exact ties", "",
        "Stable evaluation breaks score ties by original candidate order, which favors positives on RuBQ.",
        "Within exactly tied scores, put lower labels first for the low bound and higher labels first for the high bound.",
        "",
        "| Model | Queries with ties | Tied top 1 | Mixed-label tie | nDCG@10 range | MRR@10 range |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in models.items():
        ties, scores = result["ties"], result["metrics"]
        low, high = scores["nonrelevant_first"], scores["relevant_first"]
        text.append(f'| {LABELS[name]} | {ties["ties"]} | {ties["top1_tied"]} | {ties["mixed_label_tie"]} | '
                    f'{low["ndcg_at_10"]:.4f}–{high["ndcg_at_10"]:.4f} | '
                    f'{low["mrr_at_10"]:.4f}–{high["mrr_at_10"]:.4f} |')
    text += [
        "", "## Raw score agreement", "",
        "Each row compares all 3,656 aligned probability scores and counts queries whose top document changed.",
        "",
        "| Baseline | Compared with | Score MAE | Absolute error p95 | Pearson r | Top 1 changed | Gained / lost relevant top 1 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["comparisons"]:
        change = row["top1"]
        text.append(f'| {LABELS[row["base"]]} | {LABELS[row["candidate"]]} | {row["score_mae"]:.5f} | '
                    f'{row["score_abs_p95"]:.5f} | {row["score_pearson"]:.4f} | {change["changed_document"]} | '
                    f'{change["became_relevant"]} / {change["became_nonrelevant"]} |')
    text += [
        "", "## Input boundary", "",
        "Unmodified `POST /v1/rerank` used each GGUF’s embedded template. The four templates matched the",
        "Horizon wrapper byte for byte, including the single field newlines and the full assistant suffix.",
        "Each GGUF’s `/tokenize` generated separate prefix, body and suffix IDs. The body was clipped inside",
        "the 512-token total. The client supplied the longest valid document prefix up to that byte cut,",
        "tokenized the rendered prompt again, checked the suffix and ceiling, and reconciled the request’s",
        "aggregate token count against the server response.", "",
        "| Model | Body clipped | Exact target IDs | Fallback deltas (tokens → pairs) | UTF‑8 tail bytes dropped | At 512 |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for name in MODELS:
        audit = models[name]["input"]
        deltas = ", ".join(f"{delta} → {count}" for delta, count in audit["fallback_token_delta_counts"].items()) or "—"
        text.append(f'| {LABELS[name]} | {audit["target_truncated"]} | {audit["target_exact"]} | {deltas} | '
                    f'{audit["fallback_utf8_bytes_dropped"]} | {audit["effective_512"]} |')
    if "pilot-bf16" in models:
        text += ["", "The earlier BF16/MPS run used the same logical token budget via direct token submission.",
                 "It is a cross-runtime reference. The stock API consumes UTF‑8 text."]
    text += [
        "", "## Latency and memory", "",
        f'{common["chip"]}, {common["ram_bytes"] / 2**30:.0f} GiB unified memory, macOS {common["macos"]}.',
        f'llama.cpp [{common["engine_revision"][:7]}](https://github.com/ggml-org/llama.cpp/tree/{common["engine_revision"]}) '
        f'({common["engine_version"].splitlines()[0]}). All layers offloaded to Metal with Flash Attention.',
        "One server and one in-flight request at a time. Prompt caching disabled. Every timed configuration",
        f'used eight slots ({common["context_tokens_per_slot"]} runtime context tokens per slot) '
        "and a 512-token input ceiling.", "",
        "| Model | Cold ready ms | First 25 ms | 10 docs median / p95 ms | 25 docs median / p95 ms | 50 docs median / p95 ms | Peak RSS GiB | Peak footprint GiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in timing.items():
        bounds = " | ".join(f'{r["median_ms"]:.0f} / {r["p95_ms"]:.0f}' for r in result["warm"].values())
        text.append(f'| {LABELS[name]} | {result["ready_ms"]:.0f} | {result["first_25_ms"]:.0f} | {bounds} | '
                    f'{result["max_rss_bytes"] / 2**30:.2f} | {result["max_peak_footprint_bytes"] / 2**30:.2f} |')
    first = timing["yuanbao-f16"]
    texts = []
    for n, row in first["warm"].items():
        texts.append(f'{n} docs = {row["total_input_tokens"]:,} tokens '
                     f'({row["min_pair_tokens"]}–{row["max_pair_tokens"]} per pair)')
    text += [
        "",
        f'Cold metrics are medians of {first["cold_repeats"]} fresh server processes, from process launch to healthy '
        "and then for the first 25-document request. Server startup warmup was enabled and filesystem caches",
        "were left in their normal OS-managed state. Warm metrics use "
        f'{first["warm"]["10"]["repeats"]} sequential requests per size after '
        f'{first["warm"]["10"]["warmups"]} warmups, with nearest-rank p95. Inputs are nested subsets '
        "of 50 distinct 300–500-character pilot passages paired with the same RuBQ question.",
        ", ".join(texts) + ".",
        "macOS `/usr/bin/time -lp` recorded maximum resident size and peak physical footprint per process.",
        "The table takes the largest value from the cold and warmed launches. Metal shares system memory.", "",
        "See [the JSON report](rubq-pilot.json) for checksums, configuration and compact score statistics,",
        "and [the benchmark guide](../benchmark/README.md) for the raw trace filenames and reproduction commands.",
    ]
    return "\n".join(text) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sample", "raw", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--prior-scores", type=Path)
    args = parser.parse_args()
    sample = load_sample(args.sample)
    report = {"models": {}, "latency": {},
              "yuanbao_source_revision": "0101299a7937a016848d8d55b092f6e31cfa312d",
              "sample": {
        "dataset": "mteb/RuBQReranking", "revision": "f2eac2f1f82445938af650c2a285a34dd77a16eb",
        "horizon_revision": "7330f6d0b3f560af0c2b9a63820ea299a45fd91b",
        "queries": len(sample), "pairs": sum(len(q["cids"]) for q in sample),
        "positive_labels": sum(sum(label > 0 for label in q["rels"]) for q in sample),
    }}
    traces, queries = {}, {}
    protocol = ("engine_revision", "engine_version", "flags", "macos", "arch", "chip", "ram_bytes",
                "python", "pyarrow", "gguf", "sample_sha256", "template_sha256")
    fixture = None
    for name, (filename, port) in MODELS.items():
        path = args.raw / f"{name}.scores.jsonl"
        traces[name] = load_jsonl(path)
        quality = json.loads((args.raw / f"{name}.quality.run.json").read_text())
        run = json.loads((args.raw / f"{name}.latency.run.json").read_text())
        timing = json.loads((args.raw / f"{name}.latency.json").read_text())
        runtime = {key: quality[key] for key in protocol}
        require(runtime == {key: run[key] for key in protocol}, "Quality and timing environment mismatch")
        logged = verify_server_log(args.raw / f"{name}.quality.log", filename, port)
        for launch in range(1, len(timing["cold"]) + 1):
            require(logged == verify_server_log(args.raw / f"{name}.latency.launch-{launch}.log", filename, port),
                    "Metal configuration differed between launches")
        runtime.update(logged)
        require(runtime == report.setdefault("runtime", runtime), "Runtime mismatch across models")
        require({quality["sha256"], run["sha256"]} == {expected_model_sha256(filename)}
                and {quality["file"], run["file"]} == {filename}
                and {quality["port"], run["port"]} == {port}, "Run metadata does not match the pinned model and port")
        current_fixture = (
            timing["document_ids"], len(timing["cold"]),
            *(
                (timing["warm"][str(n)]["input_tokens"], len(timing["warm"][str(n)]["samples_ms"]),
                 timing["warm"][str(n)]["warmups"])
                for n in COUNTS
            ),
        )
        require(fixture is None or current_fixture == fixture, "Timing fixture differs across models")
        fixture = current_fixture
        result, queries[name] = evaluate(traces[name], sample)
        result["input"] = input_audit(traces[name], load_jsonl(args.raw / f"{name}.scores.queries.jsonl"))
        result["file"] = {key: quality[key] for key in ("file", "size_bytes", "sha256", "hub_revision")
                          if key in quality}
        result["score_trace_sha256"] = sha256(path)
        report["models"][name] = result
        report["latency"][name] = summarize_latency(timing)
        report.setdefault("date", timing["started_utc"][:10])
    fixture_ids = [row["input_ids_sha256"] for row in traces["yuanbao-f16"]]
    for name in MODELS:
        report["models"][name]["input"]["id_sequences_different_from_f16"] = sum(
            row["input_ids_sha256"] != digest for row, digest in zip(traces[name], fixture_ids, strict=True)
        )
    bases = list(combinations(MODELS, 2))
    if args.prior_scores:
        name = "pilot-bf16"
        traces[name] = load_jsonl(args.prior_scores)
        result, queries[name] = evaluate(traces[name], sample)
        result["score_trace_sha256"] = sha256(args.prior_scores)
        result["input_tokens_different_from_f16"] = sum(
            r["input_tokens"] != p["input_tokens"] for r, p in zip(
                traces["yuanbao-f16"], traces[name], strict=True
            )
        )
        report["models"][name] = result
        bases.append(("yuanbao-f16", name))
    report["comparisons"] = [compare(base, candidate, traces, queries) for base, candidate in bases]
    report["paired_bootstrap"] = paired_bootstrap(queries)
    write_json(args.raw / "rubq-per-query.json", queries)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "rubq-pilot.json", report)
    (args.out / "rubq-pilot.md").write_text(markdown(report))


if __name__ == "__main__":
    main()
