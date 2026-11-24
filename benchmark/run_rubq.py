#!/usr/bin/env python3
"""Score the fixed RuBQ pilot or time sequential requests on stock llama-server."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
from importlib.metadata import version as package_version
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import socket
import statistics
import subprocess
import time
import uuid

import gguf
import pyarrow
import pyarrow.parquet as parquet


MODELS = {
    "yuanbao-f16": ("Yuanbao-Reranker-0.6B-F16.gguf", 18091),
    "yuanbao-q8": ("Yuanbao-Reranker-0.6B-Q8_0.gguf", 18092),
    "yuanbao-q4": ("Yuanbao-Reranker-0.6B-Q4_K_M.gguf", 18093),
    "qwen-q8": ("Qwen3-Reranker-0.6B-Q8_0.gguf", 18094),
}
ENGINE = "5fddd0b99888a90260736e0f734fa8e160064e03"
QWEN_REVISION = "a02f48bb4f057028298c21fa033da2b30d7742d5"
QWEN_SHA256 = "22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48"
SAMPLE_SHA256 = "a3367f45b2650312358745c67931d004eae78233d379e570e0339719baf2b6b5"
PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements "
    "based on the Query and the Instruct provided. Note that the answer can only "
    'be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
BODY = (
    "<Instruct>: Given a web search query, retrieve relevant passages that answer "
    "the query\n<Query>: {query}\n<Document>: {document}"
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
LIMIT = 512
COUNTS = (10, 25, 50)
FLAGS = (
    "--reranking", "--host", "127.0.0.1", "--parallel", "8", "--ctx-size", "5120",
    "--batch-size", "4096", "--ubatch-size", "4096", "--device", "MTL0",
    "--gpu-layers", "all", "--flash-attn", "on", "--threads", "4", "--fit", "off",
    "--no-ui", "--no-cache-prompt", "--cache-ram", "0", "--no-kv-unified",
    "--no-context-shift", "--log-verbosity", "4",
)
TIMEOUT = 120


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def load_sample(path):
    sample = parquet.read_table(path, columns=["qid", "query", "docs", "rels", "cids"]).to_pylist()
    logical = json.dumps(sample, ensure_ascii=False, separators=(",", ":")).encode()
    require(hashlib.sha256(logical).hexdigest() == SAMPLE_SHA256, "Expected the ordered Horizon RuBQ pilot")
    require(len(sample) == 150 and sum(len(row["cids"]) for row in sample) == 3656,
            "Unexpected RuBQ pilot size")
    return sample


def model_template(model):
    reader = gguf.GGUFReader(model)
    template = reader.fields["tokenizer.chat_template.rerank"].contents()
    require(template == PREFIX + BODY + SUFFIX, f"{model.name}: embedded template differs from Horizon")
    require(reader.fields["qwen3.pooling_type"].contents() == 4, f"{model.name}: rank pooling required")
    return template


def expected_model_sha256(filename):
    if filename == "Qwen3-Reranker-0.6B-Q8_0.gguf":
        return QWEN_SHA256
    checksum_file = Path(__file__).resolve().parents[1] / "SHA256SUMS"
    checksums = {name: digest for digest, name in
                 (line.split(maxsplit=1) for line in checksum_file.read_text().splitlines() if line.strip())}
    return checksums[filename]


def checked_model_sha256(model):
    digest = sha256(model)
    require(digest == expected_model_sha256(model.name), f"{model.name}: SHA-256 differs from the expected artifact")
    return digest


@contextmanager
def server(binary, model, port, log_path):
    # A connection probe detects active listeners without binding through TCP TIME_WAIT.
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            raise RuntimeError(f"Port {port} already has a listener")
    except ConnectionRefusedError:
        pass
    pid_path = log_path.with_suffix(f".{uuid.uuid4().hex}.pid")
    command = [
        "/usr/bin/time", "-lp", "/bin/sh", "-c", 'echo "$$" > "$1"; shift; exec "$@"',
        "rerank", str(pid_path), str(binary), "-m", str(model), "--port", str(port), *FLAGS,
    ]
    environment = {k: v for k, v in os.environ.items() if not k.startswith("LLAMA_ARG_")}
    environment["LC_ALL"] = "C"
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT)
    with log_path.open("w") as log:
        started = time.perf_counter_ns()
        process = subprocess.Popen(command, stdout=log, stderr=log, env=environment)
        try:
            while True:
                if process.poll() is not None or elapsed_ms(started) > TIMEOUT * 1000:
                    raise RuntimeError(f"Server failed to become healthy. See {log_path}")
                try:
                    request(client, "/health")
                    break
                except (OSError, http.client.HTTPException):
                    client.close()
                    time.sleep(0.01)
            ready_ms = elapsed_ms(started)
            props = request(client, "/props")
            require(process.poll() is None and Path(props["model_path"]).resolve() == model.resolve(),
                    f"Server on port {port} did not load {model.name}")
            yield client, ready_ms
        finally:
            client.close()
            if process.poll() is None:
                if pid_path.exists():
                    try:
                        os.kill(int(pid_path.read_text()), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                else:
                    process.terminate()
                process.wait(timeout=TIMEOUT)
            pid_path.unlink(missing_ok=True)


def elapsed_ms(started):
    return (time.perf_counter_ns() - started) / 1e6


def request(client, route, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    client.request("GET" if payload is None else "POST", route, body, {"Content-Type": "application/json"})
    response = client.getresponse()
    data = response.read()
    if response.status != 200:
        raise http.client.HTTPException(f"{route} HTTP {response.status}: {data[:500]!r}")
    return json.loads(data)


def tokenize(client, text, pieces=False):
    return request(client, "/tokenize", {
        "content": text, "parse_special": True, "add_special": False, "with_pieces": pieces,
    })["tokens"]


def rerank(client, query, docs, expected_tokens):
    response = request(client, "/v1/rerank", {"query": query, "documents": docs, "top_n": len(docs)})
    require(response["usage"]["prompt_tokens"] == expected_tokens, "Rendered and processed token counts differ")
    rows = response["results"]
    require(sorted(row["index"] for row in rows) == list(range(len(docs))), "Invalid rerank result indices")
    scores = [row["relevance_score"] for row in rows]
    require(all(math.isfinite(score) and 0 <= score <= 1 for score in scores), "Invalid relevance score")
    require(scores == sorted(scores, reverse=True), "Scores returned out of order")
    return [row["relevance_score"] for row in sorted(rows, key=lambda row: row["index"])]


def clipped_prompt(client, head, doc, prefix_ids, suffix_ids, template):
    body = head + doc
    body_ids = tokenize(client, body)
    budget = LIMIT - len(prefix_ids) - len(suffix_ids)
    target = prefix_ids + body_ids[:budget] + suffix_ids
    truncated = len(body_ids) > budget
    proposed = doc
    utf8_tail = 0
    if truncated:
        def piece_bytes(piece):
            return piece.encode() if isinstance(piece, str) else bytes(piece)

        pieces = tokenize(client, body, pieces=True)
        require([part["id"] for part in pieces] == body_ids, "Token pieces changed IDs")
        chunks = [piece_bytes(part["piece"]) for part in pieces]
        require(b"".join(chunks) == body.encode(), "Token pieces do not reproduce the original body")
        raw = b"".join(chunks[:budget])
        boundary = raw.decode("utf-8", errors="ignore")
        utf8_tail = len(raw) - len(boundary.encode())
        require(raw.startswith(boundary.encode()) and boundary.startswith(head),
                "Token ceiling cuts the query or contains an invalid interior byte")
        proposed = boundary[len(head):]

    def render_tokens(document):
        # The pinned server substitutes each placeholder once, without rescanning inserted text.
        return tokenize(client, template + document + SUFFIX)

    encoded = render_tokens(proposed)
    initial_prefix = proposed
    while len(encoded) > LIMIT and proposed:
        proposed = proposed[:-1]
        encoded = render_tokens(proposed)
    require(len(encoded) <= LIMIT and encoded[-len(suffix_ids):] == suffix_ids,
            "Cannot preserve assistant suffix inside the token limit")
    boundary_shared = next((index for index, (a, b) in enumerate(zip(encoded, target)) if a != b),
                           min(len(encoded), len(target)))
    return proposed, {
        "input_tokens": len(encoded), "target_tokens": len(target),
        "unclipped_target_tokens": len(prefix_ids) + len(body_ids) + len(suffix_ids),
        "target_truncated": truncated, "target_exact": encoded == target,
        "target_token_delta": len(encoded) - len(target), "first_different_token": (
            None if encoded == target else boundary_shared
        ),
        "utf8_tail_bytes": utf8_tail,
        "extra_trim_bytes": len(initial_prefix.encode()) - len(proposed.encode()),
        "document_bytes_removed": len(doc.encode()) - len(proposed.encode()),
        "input_ids_sha256": hashlib.sha256(json.dumps(encoded, separators=(",", ":")).encode()).hexdigest(),
    }


def score_pilot(client, sample, template, path):
    prefix_ids, suffix_ids = tokenize(client, PREFIX), tokenize(client, SUFFIX)
    require((prefix_ids[0], suffix_ids[0]) == (151644, 151645), "Unexpected Qwen special-token IDs")
    started = time.perf_counter_ns()
    temporary = path.with_suffix(".tmp")
    temporary_ranks = path.with_suffix(".queries.tmp")
    pairs = 0
    with temporary.open("w") as output, temporary_ranks.open("w") as requests:
        for i, row in enumerate(sample):
            # Split before inserting the query to preserve literal placeholder text.
            head = BODY.split("{document}")[0].replace("{query}", row["query"])
            template_head = template.split("{document}")[0].replace("{query}", row["query"])
            docs, audits = zip(*(clipped_prompt(client, head, doc, prefix_ids, suffix_ids, template_head)
                                 for doc in row["docs"]), strict=True)
            token_count = sum(audit["input_tokens"] for audit in audits)
            scores = rerank(client, row["query"], docs, token_count)
            requests.write(json.dumps({"qid": row["qid"], "prompt_tokens": token_count}) + "\n")
            for j, (cid, label, score, audit) in enumerate(zip(
                row["cids"], row["rels"], scores, audits, strict=True,
            )):
                record = {"pair_index": pairs, "query_index": i, "candidate_index": j,
                          "qid": row["qid"], "cid": cid, "label": label, "score": score, **audit}
                output.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                pairs += 1
            if (i + 1) % 25 == 0:
                print(f"{path.stem} | {i + 1}/150 queries, {pairs}/3656 pairs, {elapsed_ms(started)/1000:.1f} s",
                      flush=True)
    require(pairs == 3656, "Incomplete score trace")
    temporary.replace(path)
    temporary_ranks.replace(path.with_suffix(".queries.jsonl"))
    return elapsed_ms(started)


def latency_fixture(sample):
    # Cap document size to hold a comparable moderate-length workload across sizes.
    documents = {}
    for row in sample:
        for cid, doc in zip(row["cids"], row["docs"], strict=True):
            if 300 <= len(doc) <= 500:
                documents.setdefault(doc, cid)
    require(len(documents) >= 50, "Insufficient distinct latency documents")
    docs = list(documents)[:50]
    return sample[0]["query"], docs, [documents[doc] for doc in docs]


def latency(binary, model, port, template, fixture, path, repeats, cold_repeats):
    query, docs, ids = fixture
    result = {"query_characters": len(query), "document_ids": ids, "cold": [], "warm": {},
              "started_utc": datetime.now(timezone.utc).isoformat()}
    for launch in range(cold_repeats):
        log = path.with_suffix(f".launch-{launch + 1}.log")
        with server(binary, model, port, log) as (client, ready):
            started = time.perf_counter_ns()
            first = request(client, "/v1/rerank", {"query": query, "documents": docs[:25], "top_n": 25})
            first_ms = elapsed_ms(started)
            head = template.split("{document}")[0].replace("{query}", query)
            lengths = [len(tokenize(client, head + doc + SUFFIX)) for doc in docs]
            require(max(lengths) <= LIMIT, "Latency fixture exceeds token ceiling")
            require(first["usage"]["prompt_tokens"] == sum(lengths[:25])
                    and len(first["results"]) == 25, "Incomplete cold request")
            cold = {"ready_ms": ready, "first_25_ms": first_ms}
            if launch == cold_repeats - 1:
                for count in COUNTS:
                    subset = docs[:count]
                    tokens = sum(lengths[:count])
                    for _ in range(2):
                        rerank(client, query, subset, tokens)
                    samples_ms = []
                    for _ in range(repeats):
                        started = time.perf_counter_ns()
                        rerank(client, query, subset, tokens)
                        samples_ms.append(elapsed_ms(started))
                    result["warm"][str(count)] = {
                        "samples_ms": samples_ms, "warmups": 2,
                        "median_ms": statistics.median(samples_ms),
                        "p95_ms": sorted(samples_ms)[math.ceil(0.95 * len(samples_ms)) - 1],
                        "input_tokens": lengths[:count], "document_characters": [len(doc) for doc in subset],
                    }
        for stat in ("maximum resident set size", "peak memory footprint"):
            match = re.search(rf"^\s*(\d+)\s+{stat}$", log.read_text(), re.MULTILINE)
            require(match is not None, f"No {stat} in {log}")
            cold[stat.replace(" ", "_") + "_bytes"] = int(match[1])
        result["cold"].append(cold)
        print(f"{path.stem} | launch {launch + 1}/{cold_repeats}, ready {ready:.1f} ms",
              flush=True)
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(path, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("quality", "latency"))
    for name in ("server", "weights", "sample", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--models", choices=MODELS, nargs="+", default=list(MODELS))
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--cold-repeats", type=int, default=3)
    args = parser.parse_args()
    require(args.repeats >= 1 and args.cold_repeats >= 1, "Repeat counts must be positive")
    sample = load_sample(args.sample)
    args.out.mkdir(parents=True, exist_ok=True)
    version = subprocess.run([args.server, "--version"], capture_output=True, text=True, check=True)
    version = (version.stdout + version.stderr).strip()
    require(ENGINE[:7] in version, "Use llama-server built at the pinned benchmark commit")
    for name in args.models:
        filename, port = MODELS[name]
        model = args.weights / filename
        model_sha256 = checked_model_sha256(model)
        template = model_template(model)
        prefix = args.out / f"{name}.{args.mode}"
        record = {
            "file": filename, "size_bytes": model.stat().st_size, "sha256": model_sha256, "engine_version": version,
            "engine_revision": ENGINE, "flags": FLAGS, "python": platform.python_version(),
            "pyarrow": pyarrow.__version__, "gguf": package_version("gguf"),
            "macos": platform.mac_ver()[0], "arch": platform.machine(), "port": port,
            "chip": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
            "ram_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])),
            "sample_sha256": SAMPLE_SHA256, "sample_file_sha256": sha256(args.sample),
            "template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        }
        if args.mode == "quality":
            with server(args.server, model, port, prefix.with_name(prefix.name + ".log")) as (client, _):
                record["scoring_ms"] = score_pilot(client, sample, template, args.out / f"{name}.scores.jsonl")
        else:
            latency(args.server, model, port, template, latency_fixture(sample),
                    prefix.with_name(prefix.name + ".json"), args.repeats, args.cold_repeats)
        if name == "qwen-q8":
            record["hub_revision"] = QWEN_REVISION
        write_json(prefix.with_name(prefix.name + ".run.json"), record)


if __name__ == "__main__":
    main()
