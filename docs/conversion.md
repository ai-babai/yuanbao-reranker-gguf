---
type: Build Guide
description: Build the pinned llama.cpp tools and reproduce the three Yuanbao reranker GGUF variants.
created: "2026-11-24"
---

# Build the Yuanbao reranker GGUFs

The recipe pins the Yuanbao BF16 checkpoint to `0101299a7937a016848d8d55b092f6e31cfa312d` and llama.cpp to `5fddd0b99888a90260736e0f734fa8e160064e03`. [Yuanbao checkpoint](https://huggingface.co/Yuanbao-Search/Yuanbao-Reranker-0.6B/tree/0101299a7937a016848d8d55b092f6e31cfa312d) · [llama.cpp source](https://github.com/ggml-org/llama.cpp/tree/5fddd0b99888a90260736e0f734fa8e160064e03)

The artifacts were built on Apple Silicon with Git, CMake, the Xcode toolchain and uv. Keep the artifact root and checkpoint outside the repository. Allow about 3.4 GB for the three outputs and their temporary BF16 intermediate, plus space for the source checkpoint, build and Python environment.

From the repository root, substitute your own paths.

```sh
ROOT=../yuanbao-artifacts/gguf
CHECKPOINT=../yuanbao-artifacts/checkpoint
scripts/convert-build.sh "$ROOT"
```

The script builds `llama-server` and `llama-quantize` in `$ROOT/tools/llama.cpp/build/bin`. Keep the shared libraries in that directory with the executables. The converter uses CPython 3.12.11, PyTorch 2.11.0 and Transformers 4.57.6. The dependency lock is [convert-requirements.txt](../scripts/convert-requirements.txt).

Reuse a local copy of the pinned checkpoint if available. To fetch the five required files from the public upstream repository, run the following command.

```sh
HF_HOME="$ROOT/tools/hf-cache" "$ROOT/tools/convert-venv/bin/hf" download \
  Yuanbao-Search/Yuanbao-Reranker-0.6B \
  config.json generation_config.json model.safetensors tokenizer.json tokenizer_config.json \
  --revision 0101299a7937a016848d8d55b092f6e31cfa312d --local-dir "$CHECKPOINT"
```

```sh
"$ROOT/tools/convert-venv/bin/python" -B scripts/convert_yuanbao.py "$ROOT" "$CHECKPOINT"
```

The converter verifies the SHA-256 of each source file. It builds the F16 file from the source tensors and quantizes Q8_0 and Q4_K_M independently from a temporary BF16 GGUF. Both quants use the pinned `llama-quantize` without an importance matrix. All three retain the same F32 classifier. Each verified file is moved into place atomically.

- `$ROOT/weights/Yuanbao-Reranker-0.6B-F16.gguf`
- `$ROOT/weights/Yuanbao-Reranker-0.6B-Q8_0.gguf`
- `$ROOT/weights/Yuanbao-Reranker-0.6B-Q4_K_M.gguf`

## Classifier and prompt

The converter explicitly selects the upstream Qwen3 reranker path. The `cls.output.weight` tensor contains rows 9693 (`yes`) and 2152 (`no`) from the tied embeddings, in that order. Causal rank pooling selects the last prompt token. The runtime applies a two-class softmax to the logits and `/v1/rerank` returns the first class probability, `P(yes) = sigmoid(logit_yes - logit_no)`. Consumers can use the score directly. [Rank pooling implementation](https://github.com/ggml-org/llama.cpp/blob/5fddd0b99888a90260736e0f734fa8e160064e03/src/llama-graph.cpp) · [Server scoring](https://github.com/ggml-org/llama.cpp/blob/5fddd0b99888a90260736e0f734fa8e160064e03/tools/server/server-context.cpp)

The GGUF's `tokenizer.chat_template.rerank` starts directly with `<|im_start|>system`. The instruction, query and document use single newline separators. The assistant wrapper ends with the exact escaped suffix `<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n`. The converter checks the serialized template and the classifier rows before moving each file into place. [Horizon reference scorer](https://huggingface.co/Horizon-Labs/multilingual-reranker-base/blob/7330f6d0b3f560af0c2b9a63820ea299a45fd91b/code/rerank/eval_rerank.py)

For exact pilot comparisons, encode the prefix, body and suffix separately with special-token insertion disabled. Keep the first 464 body tokens between the 39-token prefix and nine-token suffix. The resulting input is at most 512 tokens. The stock `/v1/rerank` handler renders and tokenizes the whole string, and its context setting does not implement this suffix-preserving cut. Use explicit token IDs for exact pilot scoring or verify that a clipped document string retokenizes to the same IDs before sending it to the HTTP endpoint.

## Score verification

A Metal spot check used 12 paired examples from the RuBQ BF16 pilot. It included four inputs clipped to 512 tokens. The F16 server token IDs matched the pilot IDs for all 12, using a verified client-side document cut for the four long inputs. The HTTP scores agreed with direct F16 rank pooling within `4.7e-10`. The F16 classifier path agreed with softmax over the full F16 language-model logits for `yes` and `no` within `2.45e-4`.

| Variant | Mean absolute difference from BF16 | Maximum absolute difference from BF16 |
| --- | ---: | ---: |
| F16 | 0.00261 | 0.01311 |
| Q8_0 | 0.00385 | 0.02107 |
| Q4_K_M | 0.02555 | 0.15026 |

The table measures probability differences on the 12 checked pairs. The maximum F16 difference among the clipped pairs was 0.00615.
