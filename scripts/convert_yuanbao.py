#!/usr/bin/env python3
"""Build the three release GGUFs from the pinned Yuanbao checkpoint."""

import argparse
import hashlib
import logging
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

NAME = "Yuanbao-Reranker-0.6B"
SOURCE = f"https://huggingface.co/Yuanbao-Search/{NAME}"
SOURCE_REVISION = "0101299a7937a016848d8d55b092f6e31cfa312d"
LLAMA_REVISION = "5fddd0b99888a90260736e0f734fa8e160064e03"
SOURCE_HASHES = {
    "config.json": "48d60f3a8b44c23dc5fc76a247ccfc3876cf011472eda340bc5d1588620c5938",
    "generation_config.json": "ea2309a9a3340059939037ff53f87761b8ede5b7cf7ff5693cf4bbd9be4d7765",
    "model.safetensors": "5518577ec411e854485f0424a67dd93729a17c1f9f500200f4ce3438ee3477e1",
    "tokenizer.json": "be75606093db2094d7cd20f3c2f385c212750648bd6ea4fb2bf507a6a4c55506",
    "tokenizer_config.json": "397bdca5697f44ab70a567f196203e396fc904b1891bb79fc107e304fb3d8f2c",
}

# The pinned Qwen3 converter already emits this template. Check the serialized bytes
# to catch changes to the instruction, field separators or final pooled token.
RERANK_TEMPLATE = (
    '<|im_start|>system\n'
    'Judge whether the Document meets the requirements based on the Query and the Instruct provided. '
    'Note that the answer can only be "yes" or "no".<|im_end|>\n'
    '<|im_start|>user\n'
    '<Instruct>: Given a web search query, retrieve relevant passages that answer the query\n'
    '<Query>: {query}\n'
    '<Document>: {document}<|im_end|>\n'
    '<|im_start|>assistant\n<think>\n\n</think>\n\n'
)
CLASSIFIER = "cls.output.weight"
LABELS = ["yes", "no"]
LABEL_IDS = [9693, 2152]


def verify_gguf(path, file_type, classifier_rows):
    import gguf
    import numpy as np

    reader = gguf.GGUFReader(path)
    expected = {
        "general.architecture": "qwen3",
        "general.file_type": int(file_type),
        "qwen3.pooling_type": int(gguf.PoolingType.RANK),
        "qwen3.classifier.output_labels": LABELS,
        "tokenizer.chat_template.rerank": RERANK_TEMPLATE,
    }
    for key, value in expected.items():
        field = reader.get_field(key)
        if field is None or field.contents() != value:
            raise ValueError(f"{path.name}: unexpected {key}")
    tokens = reader.get_field("tokenizer.ggml.tokens")
    if [tokens.contents(index) for index in LABEL_IDS] != LABELS:
        raise ValueError(f"{path.name}: label token IDs do not match the vocabulary")
    classifier = next(tensor for tensor in reader.tensors if tensor.name == CLASSIFIER)
    if classifier.tensor_type != gguf.GGMLQuantizationType.F32:
        raise ValueError(f"{path.name}: expected an F32 classifier")
    np.testing.assert_array_equal(classifier.data, classifier_rows)


def run_quantizer(binary, source, output, variant):
    result = subprocess.run(
        [binary, "--tensor-type", r"^cls\.output\.weight$=f32", source, output, variant],
        stderr=subprocess.PIPE,
        text=True,
    )
    sys.stderr.write(result.stderr)
    result.check_returncode()
    # This revision prints its build banner during quantization.
    build = re.search(r"^version: .*\(build \d+, commit ([0-9a-f]{7,40})\)$", result.stderr, re.MULTILINE)
    if build is None or not LLAMA_REVISION.startswith(build[1]):
        raise ValueError(f"{binary}: expected a build from llama.cpp {LLAMA_REVISION}")


def convert(root, source):
    llama = root / "tools" / "llama.cpp"
    revision = subprocess.check_output(["git", "-C", llama, "rev-parse", "HEAD"], text=True).strip()
    modified = subprocess.check_output(
        ["git", "-C", llama, "status", "--porcelain", "--untracked-files=no"], text=True
    ).strip()
    if revision != LLAMA_REVISION or modified:
        raise ValueError(f"Expected a clean llama.cpp checkout at {LLAMA_REVISION}")

    sys.path[:0] = [str(llama), str(llama / "gguf-py")]
    from conversion.qwen import Qwen3Model
    import numpy as np
    import gguf
    from safetensors import safe_open

    class YuanbaoModel(Qwen3Model):
        model_arch = Qwen3Model.model_arch

        def _is_qwen3_reranker(self):
            return True

        def _find_rerank_config(self):
            super()._find_rerank_config()
            if not self.is_tied_embeddings or [self.token_true_id, self.token_false_id] != LABEL_IDS:
                raise ValueError("Expected tied embeddings and the pinned yes/no token IDs")

        def tensor_force_quant(self, name, new_name, bid, n_dims):
            if new_name == CLASSIFIER:
                return gguf.GGMLQuantizationType.F32
            return super().tensor_force_quant(name, new_name, bid, n_dims)

        def set_gguf_parameters(self):
            super().set_gguf_parameters()
            self.gguf_writer.add_license("apache-2.0")
            self.gguf_writer.add_source_repo_url(SOURCE)
            self.gguf_writer.add_source_url(f"{SOURCE}/tree/{SOURCE_REVISION}")

    weights = root / "weights"
    weights.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".convert-", dir=weights) as work:
        work = Path(work)
        checkpoint = work / "checkpoint"
        checkpoint.mkdir()
        # Whitelist the checkpoint files so sidecars cannot change the export.
        for filename, expected in SOURCE_HASHES.items():
            path = source / filename
            with path.open("rb") as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            if actual != expected:
                raise ValueError(f"SHA-256 mismatch for {filename} at source revision {SOURCE_REVISION}")
            (checkpoint / filename).symlink_to(path)

        with safe_open(checkpoint / "model.safetensors", framework="pt") as model:
            embedding = model.get_slice("model.embed_tokens.weight")
            classifier_rows = np.stack([embedding[index, :].float().numpy() for index in LABEL_IDS])

        file_types = gguf.LlamaFileType

        def publish(variant, file_type, path):
            verify_gguf(path, file_type, classifier_rows)
            destination = weights / f"{NAME}-{variant}.gguf"
            path.replace(destination)
            print(destination, flush=True)

        f16 = work / "model-f16.gguf"
        YuanbaoModel(checkpoint, file_types.MOSTLY_F16, f16, model_name=NAME).write()
        publish("F16", file_types.MOSTLY_F16, f16)

        bf16 = work / "model-bf16.gguf"
        YuanbaoModel(checkpoint, file_types.MOSTLY_BF16, bf16, model_name=NAME).write()
        quantize = llama / "build" / "bin" / "llama-quantize"
        for variant, file_type in [
            ("Q8_0", file_types.MOSTLY_Q8_0),
            ("Q4_K_M", file_types.MOSTLY_Q4_K_M),
        ]:
            output = work / f"model-{variant}.gguf"
            run_quantizer(quantize, bf16, output, variant)
            publish(variant, file_type, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("checkpoint", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    convert(args.artifact_root.resolve(), args.checkpoint.resolve())


if __name__ == "__main__":
    main()
