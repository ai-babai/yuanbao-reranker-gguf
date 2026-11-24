---
type: Benchmark Report
description: Linux CPU reranking latency and HTTP behavior for the Yuanbao Q8_0 and Q4_K_M GGUFs on the fixed RuBQ timing fixture.
created: "2026-11-24"
---

# Yuanbao GGUF on Linux CPU

Both GGUFs ran on the same Ubuntu 26.04.1 LTS x86-64 guest with four AMD EPYC 7763 vCPUs and 11.7 GiB RAM. Each run used one server, one in-flight request, affinity to three vCPUs, and nice level +15. The stock engine was llama.cpp `b12676` at `d35dc4d9e6827db8e08426a2340d8a71ea863cd9`. The [Metal pilot](rubq-pilot.md) used a different engine revision. Interpret timings within this Linux guest. [Stock Linux release](https://github.com/ggml-org/llama.cpp/releases/tag/b12676)

| Model | Startup to healthy (s) | Peak RSS (MiB) | 10 docs, median [range] (s) | 25 docs, median [range] (s) | 50 docs, median [range] (s) |
|---|---:|---:|---:|---:|---:|
| Yuanbao Q8_0 | 1.96 | 1,374.5 | 14.18 [13.93–14.30] | 35.87 [35.01–36.86] | 70.63 [70.20–71.06] |
| Yuanbao Q4_K_M | 2.11 | 1,347.3 | 11.71 [11.52–11.76] | 28.95 [28.74–28.98] | 57.62 [57.27–57.98] |

Q4_K_M had 17–19% lower warm medians across the three request sizes. Its peak RSS was 27 MiB lower and its GGUF was 38% smaller than Q8_0.

Startup is one fresh-process observation per model, with default engine warmup and normal filesystem cache state after weight checksum verification. The server received two short semantic probes and one untimed 10-document request before timed requests. Warm timings include loopback HTTP and JSON decoding. There are three samples for 10 and 25 documents and two for 50, where each request takes about a minute on this guest. Peak RSS is GNU `/usr/bin/time -v` maximum resident set size for the server process.

The same RuBQ question and nested groups of 10, 25 and 50 passages used by the Metal pilot contributed 2,341, 5,761 and 11,440 total prompt tokens. Each original passage contains 304–497 characters and every rendered query–passage prompt contains 187–293 tokens. All 50 prompt token sequences matched for both quants, and the logs confirmed zero reused prompt tokens. The process reported AVX2, FMA and Flash Attention enabled, with zero GPU layers. [Pinned RuBQ data](https://huggingface.co/datasets/mteb/RuBQReranking/tree/f2eac2f1f82445938af650c2a285a34dd77a16eb)

## Reproduce the request

Use the [Ubuntu x64 release archive](https://github.com/ggml-org/llama.cpp/releases/download/b12676/llama-b12676-bin-ubuntu-x64.tar.gz) and check its SHA-256 against [linux-cpu.json](linux-cpu.json). If the loader needs `libgomp.so.1`, unpack the matching Ubuntu `libgomp1` package in your run directory with `dpkg-deb -x` and point that process's `LD_LIBRARY_PATH` to the unpacked library directory. Verify the model against [SHA256SUMS](../SHA256SUMS) and set `MODEL` to the verified GGUF path. Use a quiet CPU host and adjust the affinity list to leave one vCPU available to other work.

```sh
OMP_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 /usr/bin/time -v \
  nice -n 15 taskset -c 1-3 ./llama-b12676/llama-server -m "$MODEL" \
  --reranking --host 127.0.0.1 --port 18095 --no-ui \
  --device none --gpu-layers 0 --no-op-offload --threads 3 --threads-batch 3 \
  --threads-http 2 --parallel 8 --ctx-size 5120 --batch-size 4096 --ubatch-size 4096 \
  --flash-attn on --no-cache-prompt --cache-ram 0 --no-kv-unified \
  --no-context-shift --fit off --log-verbosity 4
```

Once `/health` returns OK, run this smoke check with the server in a second terminal. Both quants returned index 1 for the subscription query and index 0 for the password query.

```sh
for q in 'Как отключить автопродление подписки?' 'Где поменять пароль?'; do
  jq -nc --arg q "$q" '{query:$q,documents:[
    "Для изменения пароля откройте настройки безопасности.",
    "Откройте раздел подписок и выключите автоматическое продление."],top_n:2}' |
    curl -fsS http://127.0.0.1:18095/v1/rerank -H 'Content-Type: application/json'       --data-binary @- |
    jq '.results'
done
```

To generate the timed payloads, prepare the pinned parquet and Python environment from the [benchmark guide](../benchmark/README.md). Set `SAMPLE` to the parquet path and `RUN_DIR` to an external output directory. From the repository root, reuse the Metal benchmark's fixture selection.

```sh
PYTHONPATH=benchmark "$PY" -B - "$SAMPLE" "$RUN_DIR" <<'PY'
import json
from pathlib import Path
import sys
from run_rubq import latency_fixture, load_sample

sample, output = map(Path, sys.argv[1:])
query, docs, ids = latency_fixture(load_sample(sample))
for count in (10, 25, 50):
    payload = {"query": query, "documents": docs[:count], "top_n": count}
    (output / f"request-{count}.json").write_text(json.dumps(payload, ensure_ascii=False))
PY
curl -fsS -H 'Content-Type: application/json' --data-binary @"$RUN_DIR/request-10.json" \
  -w '\n%{time_total} s\n' http://127.0.0.1:18095/v1/rerank
```

[JSON results](linux-cpu.json) contains the individual timings, exact flags, file checksums, and smoke-test scores.
