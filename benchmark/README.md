---
type: Benchmark Guide
description: Reproduce the pinned stock llama.cpp evaluation for the RuBQ pilot and the Apple Metal latency measurements.
created: "2026-11-24"
---

# Reproduce the RuBQ pilot

Use a stock Metal-enabled `llama-server` at commit `5fddd0b99888a90260736e0f734fa8e160064e03`. Build it and the Yuanbao GGUFs following the [conversion guide](../docs/conversion.md). Run the commands below from the checkout with an external artifact directory and a local copy of the pinned llama.cpp source. Put the three Yuanbao GGUFs under `weights/`, with the filenames from the conversion guide.

```sh
ARTIFACTS=/path/to/artifacts
LLAMA_CPP=/path/to/llama.cpp
mkdir -p "$ARTIFACTS/weights" "$ARTIFACTS/bench"
export UV_CACHE_DIR="$ARTIFACTS/uv-cache"
export HF_HOME="$ARTIFACTS/hf-cache"
uv venv --python 3.12 "$ARTIFACTS/benchmark-venv"
PY="$ARTIFACTS/benchmark-venv/bin/python"
uv pip install --python "$PY" 'pyarrow==25.0.1' 'numpy==2.5.5' "$LLAMA_CPP/gguf-py"

url=https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF
revision=a02f48bb4f057028298c21fa033da2b30d7742d5
file="$ARTIFACTS/weights/Qwen3-Reranker-0.6B-Q8_0.gguf"
curl --fail --location "$url/resolve/$revision/qwen3-reranker-0.6b-q8_0.gguf" -o "$file"
printf '%s  %s\n' 22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48 "$file" |
  shasum -a 256 -c -

uv run --script scripts/prepare_rubq.py "$ARTIFACTS/bench/rubq.parquet"
for mode in quality latency; do
  "$PY" -B benchmark/run_rubq.py "$mode" \
    --server "$LLAMA_CPP/build/bin/llama-server" --weights "$ARTIFACTS/weights" \
    --sample "$ARTIFACTS/bench/rubq.parquet" --out "$ARTIFACTS/bench"
done
"$PY" -B benchmark/summarize_rubq.py \
  --sample "$ARTIFACTS/bench/rubq.parquet" --raw "$ARTIFACTS/bench" --out results
```

For the earlier BF16/MPS comparison, pass the corresponding uncompressed trace via `--prior-scores /path/to/scores.jsonl` to the summarizer. The trace needs the original candidate order and the fields `qid`, `cid`, `label`, `score` and `input_tokens`.

The quality runner verifies the ordered sample, each embedded GGUF template and rank pooling. It computes the original prompt budget with the model tokenizer, turns the clipped token span into the longest valid document prefix up to the byte cut, and tokenizes the complete prompt again before posting the text to `/v1/rerank`. It uses the original Horizon wrapper and instruction. Raw scores are the probability returned by the server. The evaluator uses the original candidate order for exact ties and also calculates lower and upper bounds by rearranging labels within tied groups. For the two Q8_0 models it bootstraps the paired per-query metric differences using 10,000 shared query resamples with replacement and PCG64 seed 0.

The timing run requires a quiet Apple Metal host. Each model uses a separate loopback port within 18091–18094. Run the timing pass without other inference or builds. The harness records fresh-process startup and the first 25-document request, then warmed median and nearest-rank p95 for 10, 25 and 50 documents. OS filesystem cache is left under normal OS management. All requests use the same RuBQ question and the same nested sample of passages. This isolates the effects of candidate count on the endpoint.

## Output files

### Recalculate the published report without running inference

Download `RuBQ150-GGUF-benchmark.tar.gz`, `RuBQ150-BF16-scores.jsonl.gz` and `SHA256SUMS` from the [v0.1.0 release](https://github.com/ai-babai/yuanbao-reranker-gguf/releases/tag/v0.1.0) into `$ARTIFACTS`. Use the Python environment installed above. The archive contains the four complete score traces, timing samples and server log excerpts. With the released files these commands reproduce the Markdown and JSON reports byte for byte.

```sh
(cd "$ARTIFACTS" && grep 'RuBQ150-' SHA256SUMS | shasum -a 256 -c -)
tar -xzf "$ARTIFACTS/RuBQ150-GGUF-benchmark.tar.gz" -C "$ARTIFACTS"
gzip -dc "$ARTIFACTS/RuBQ150-BF16-scores.jsonl.gz" > "$ARTIFACTS/bf16.jsonl"
uv run --script scripts/prepare_rubq.py "$ARTIFACTS/bench/rubq.parquet"
"$PY" -B benchmark/summarize_rubq.py \
  --sample "$ARTIFACTS/bench/rubq.parquet" --raw "$ARTIFACTS/bench" \
  --prior-scores "$ARTIFACTS/bf16.jsonl" --out "$ARTIFACTS/recomputed"
cmp "$ARTIFACTS/recomputed/rubq-pilot.json" "$ARTIFACTS/results/rubq-pilot.json"
```

### Artifact contents

- `bench/*.scores.jsonl` contains the complete score and token-boundary trace by candidate.
- `bench/*.scores.queries.jsonl` contains the server-verified prompt-token count by query.
- `bench/*.quality.run.json`, `bench/*.latency.run.json` and `bench/*.log` capture runtime, model checksums and server output.
- `bench/*.latency.json` contains raw request times, per-pair lengths and memory measurements.
- `bench/rubq-per-query.json` contains the per-query ranking and tie metrics.
- `results/rubq-pilot.json` and `results/rubq-pilot.md` are the generated summaries.
