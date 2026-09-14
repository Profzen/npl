from __future__ import annotations

import hashlib
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = PROJECT_ROOT / "models" / "qwen2.5-coder-7b"
TARGET = TARGET_DIR / "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
URL = "https://modelscope.cn/models/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/master/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
TOTAL_BYTES = 4_683_073_536
EXPECTED_SHA256 = "509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c"
SEGMENT_COUNT = 64
SEGMENT_SIZE = (TOTAL_BYTES + SEGMENT_COUNT - 1) // SEGMENT_COUNT
WORKERS = max(1, min(32, int(os.getenv("AUDITAI_DOWNLOAD_WORKERS", "16"))))
_PRINT_LOCK = threading.Lock()


def report(message: str) -> None:
    with _PRINT_LOCK:
        print(message, flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download_piece(index: int) -> None:
    start = index * SEGMENT_SIZE
    end = min(TOTAL_BYTES - 1, (index + 1) * SEGMENT_SIZE - 1)
    expected = end - start + 1
    path = TARGET_DIR / f"piece-{index:02d}.bin"
    if path.exists() and path.stat().st_size > expected:
        raise RuntimeError(f"Le segment {index} dépasse sa taille attendue.")
    while (path.stat().st_size if path.exists() else 0) < expected:
        current = path.stat().st_size if path.exists() else 0
        request = urllib.request.Request(
            URL,
            headers={
                "Range": f"bytes={start + current}-{end}",
                "User-Agent": "AuditAI-local-model-downloader/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status != 206:
                    raise RuntimeError(f"HTTP {response.status}; réponse partielle attendue")
                deadline = time.monotonic() + 30
                with path.open("ab") as output:
                    while block := response.read(1024 * 1024):
                        output.write(block)
                        if time.monotonic() >= deadline:
                            break
        except Exception as exc:
            report(f"Segment {index}: reprise à {current}/{expected} après {type(exc).__name__}")
            time.sleep(2)
    report(f"Segment {index}: terminé")


def main() -> None:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    if TARGET.exists() and TARGET.stat().st_size == TOTAL_BYTES:
        actual_hash = sha256(TARGET)
        if actual_hash == EXPECTED_SHA256:
            print(f"Le modèle 7B est déjà complet et vérifié : {TARGET}")
            return
        raise RuntimeError("Le fichier 7B existant a une empreinte SHA-256 invalide.")

    print(f"Téléchargement reprenable avec {WORKERS} connexions.")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(download_piece, range(SEGMENT_COUNT)))

    temporary = TARGET.with_suffix(".gguf.assembling")
    with temporary.open("wb") as output:
        for index in range(SEGMENT_COUNT):
            with (TARGET_DIR / f"piece-{index:02d}.bin").open("rb") as source:
                while block := source.read(8 * 1024 * 1024):
                    output.write(block)
    if temporary.stat().st_size != TOTAL_BYTES:
        raise RuntimeError(f"Taille assemblée invalide : {temporary.stat().st_size}/{TOTAL_BYTES}")
    actual_hash = sha256(temporary)
    if actual_hash != EXPECTED_SHA256:
        raise RuntimeError(f"Empreinte SHA-256 invalide : {actual_hash}")
    temporary.replace(TARGET)
    for index in range(SEGMENT_COUNT):
        (TARGET_DIR / f"piece-{index:02d}.bin").unlink(missing_ok=True)
    print(f"Modèle complet et vérifié : {TARGET}")


if __name__ == "__main__":
    main()

