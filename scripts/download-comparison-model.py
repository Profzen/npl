from __future__ import annotations

import argparse
import hashlib
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "qwen3": {
        "url": "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf",
        "target": ROOT / "models" / "qwen3-4b" / "qwen3-4b-q4_k_m.gguf",
        "bytes": 2_497_280_256,
        "sha256": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
    },
    "gemma3": {
        "url": "https://huggingface.co/ggml-org/gemma-3-4b-it-GGUF/resolve/main/gemma-3-4b-it-Q4_K_M.gguf",
        "target": ROOT / "models" / "gemma3-4b" / "gemma-3-4b-it-q4_k_m.gguf",
        "bytes": 2_489_757_856,
        "sha256": "882e8d2db44dc554fb0ea5077cb7e4bc49e7342a1f0da57901c0802ea21a0863",
    },
}
SEGMENTS = 32
WORKERS = max(1, min(16, int(os.getenv("AUDITAI_DOWNLOAD_WORKERS", "8"))))
LOCK = threading.Lock()


def report(message: str) -> None:
    with LOCK:
        print(message, flush=True)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download(model_name: str) -> None:
    spec = MODELS[model_name]
    target: Path = spec["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    total = int(spec["bytes"])
    segment_size = (total + SEGMENTS - 1) // SEGMENTS

    if target.exists() and target.stat().st_size == total:
        if file_hash(target) == spec["sha256"]:
            print(f"{model_name}: fichier déjà complet et vérifié")
            return
        raise RuntimeError(f"{model_name}: empreinte du fichier final invalide")

    def piece(index: int) -> None:
        start = index * segment_size
        end = min(total - 1, (index + 1) * segment_size - 1)
        expected = end - start + 1
        path = target.parent / f".{model_name}-piece-{index:02d}.bin"
        if path.exists() and path.stat().st_size > expected:
            path.unlink()
        while (path.stat().st_size if path.exists() else 0) < expected:
            current = path.stat().st_size if path.exists() else 0
            request = urllib.request.Request(
                str(spec["url"]),
                headers={
                    "Range": f"bytes={start + current}-{end}",
                    "User-Agent": "AuditAI-model-comparison/1.0",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    if response.status != 206:
                        raise RuntimeError(f"HTTP {response.status}, 206 attendu")
                    deadline = time.monotonic() + 30
                    with path.open("ab") as output:
                        while block := response.read(1024 * 1024):
                            output.write(block)
                            if time.monotonic() >= deadline:
                                break
            except Exception as exc:
                report(f"{model_name} segment {index}: reprise après {type(exc).__name__}")
                time.sleep(2)
        report(f"{model_name} segment {index}: terminé")

    print(f"{model_name}: {SEGMENTS} segments, {WORKERS} connexions")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(piece, range(SEGMENTS)))

    assembling = target.with_suffix(".gguf.assembling")
    with assembling.open("wb") as output:
        for index in range(SEGMENTS):
            part = target.parent / f".{model_name}-piece-{index:02d}.bin"
            with part.open("rb") as source:
                while block := source.read(8 * 1024 * 1024):
                    output.write(block)
    if assembling.stat().st_size != total:
        raise RuntimeError(f"{model_name}: taille assemblée invalide")
    actual = file_hash(assembling)
    if actual != spec["sha256"]:
        raise RuntimeError(f"{model_name}: SHA-256 invalide {actual}")
    assembling.replace(target)
    for index in range(SEGMENTS):
        (target.parent / f".{model_name}-piece-{index:02d}.bin").unlink(missing_ok=True)
    print(f"{model_name}: complet et vérifié: {target}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=sorted(MODELS))
    args = parser.parse_args()
    download(args.model)


if __name__ == "__main__":
    main()
