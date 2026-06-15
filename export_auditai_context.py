import os
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent

OUTPUT_DIR = ROOT / "auditai_export_output"
ZIP_PATH = ROOT / "auditai_context_export.zip"

MAX_SIZE = 20 * 1024 * 1024  # 20 MB par fichier txt

EXCLUDED_DIRS = {
    ".git",
    ".next",
    "node_modules",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".turbo",
    "coverage",
    "auditai_export_output",
}

EXCLUDED_EXTENSIONS = {
    ".gguf",
    ".safetensors",
    ".onnx",
    ".pt",
    ".pth",
    ".ckpt",
    ".dll",
    ".exe",
    ".bin",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".mp3",
    ".wav",
    ".pdf",
}

EXCLUDED_FILES = {
    "auditai_manifest.txt",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".DS_Store",
    "auditai_context_export.zip",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".scss",
    ".json",
    ".yaml",
    ".yml",
    ".env",
    ".txt",
    ".md",
    ".sql",
    ".sh",
    ".bat",
    ".toml",
    ".ini",
    ".ipynb",
    ".jinja",
    ".j2",
    ".csv",
}

SECRET_WORDS = {
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASS",
    "API_KEY",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "DATABASE_URL",
    "DB_URL",
    "JWT",
}


def prepare_output():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()


def is_excluded_dir(dirname: str) -> bool:
    return dirname in EXCLUDED_DIRS or dirname.startswith("checkpoint-")


def should_skip(path: Path) -> bool:
    for part in path.parts:
        if is_excluded_dir(part):
            return True

    if path.name.startswith("auditai_export_part_"):
        return True

    if path.name in EXCLUDED_FILES:
        return True

    if path.suffix.lower() in EXCLUDED_EXTENSIONS:
        return True

    return False


def redact_env_content(content: str) -> str:
    lines = []

    for line in content.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue

        key, value = line.split("=", 1)
        key_upper = key.upper()

        if any(secret in key_upper for secret in SECRET_WORDS):
            lines.append(f"{key}=<REDACTED>")
        else:
            lines.append(line)

    return "\n".join(lines)


def notebook_to_text(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            notebook = json.load(f)

        content = []

        content.append(f"# NOTEBOOK: {path.name}\n")
        content.append("# Outputs non exportés. Seuls le code et le markdown sont conservés.\n\n")

        for i, cell in enumerate(notebook.get("cells", []), start=1):
            cell_type = cell.get("cell_type", "unknown")
            source = cell.get("source", [])

            content.append("\n")
            content.append("=" * 80 + "\n")
            content.append(f"CELL {i} | TYPE: {cell_type}\n")
            content.append("=" * 80 + "\n\n")

            if isinstance(source, list):
                content.extend(source)
            else:
                content.append(str(source))

            content.append("\n")

        return "".join(content)

    except Exception as e:
        return f"[NOTEBOOK ERROR] {e}"


class ExportWriter:
    def __init__(self):
        self.part = 1
        self.current_size = 0
        self.file = self._open_part()

    def _open_part(self):
        output_path = OUTPUT_DIR / f"auditai_export_part_{self.part}.txt"
        return open(output_path, "w", encoding="utf-8")

    def write(self, text: str):
        encoded = text.encode("utf-8")

        if self.current_size + len(encoded) > MAX_SIZE:
            self.file.close()
            self.part += 1
            self.current_size = 0
            self.file = self._open_part()

        self.file.write(text)
        self.current_size += len(encoded)

    def close(self):
        self.file.close()


def build_tree() -> str:
    lines = []

    for root, dirs, files in os.walk(ROOT):
        root_path = Path(root)

        dirs[:] = [
            d for d in dirs
            if not is_excluded_dir(d)
        ]

        level = len(root_path.relative_to(ROOT).parts)
        indent = "    " * level

        if root_path == ROOT:
            lines.append(f"{ROOT.name}/")
        else:
            lines.append(f"{indent}{root_path.name}/")

        for file in sorted(files):
            path = root_path / file

            if should_skip(path):
                continue

            lines.append(f"{indent}    {file}")

    return "\n".join(lines)


def read_file_content(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".ipynb":
        return notebook_to_text(path)

    content = path.read_text(encoding="utf-8", errors="ignore")

    if path.name == ".env" or suffix == ".env":
        return redact_env_content(content)

    return content


def export_files(writer: ExportWriter) -> int:
    exported = 0

    for root, dirs, files in os.walk(ROOT):
        root_path = Path(root)

        dirs[:] = [
            d for d in dirs
            if not is_excluded_dir(d)
        ]

        for file in sorted(files):
            path = root_path / file

            if should_skip(path):
                continue

            if path.suffix.lower() not in TEXT_EXTENSIONS:
                continue

            exported += 1

            writer.write("\n\n")
            writer.write("=" * 100 + "\n")
            writer.write(f"FILE : {path.relative_to(ROOT)}\n")
            writer.write("=" * 100 + "\n\n")

            try:
                content = read_file_content(path)
                writer.write(content)
            except Exception as e:
                writer.write(f"[READ ERROR] {e}")

            writer.write("\n")

    return exported


def create_manifest(exported_count: int, parts: int) -> Path:
    manifest = OUTPUT_DIR / "auditai_manifest.txt"

    with open(manifest, "w", encoding="utf-8") as f:
        f.write("AUDITAI MANIFEST\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Generated : {datetime.now()}\n")
        f.write(f"Project root : {ROOT}\n\n")
        f.write(f"Exported files : {exported_count}\n")
        f.write(f"Export parts : {parts}\n\n")

        for i in range(1, parts + 1):
            f.write(f"auditai_export_part_{i}.txt\n")

    return manifest


def create_zip() -> Path:
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file_path in sorted(OUTPUT_DIR.glob("*.txt")):
            zipf.write(
                file_path,
                arcname=file_path.name
            )

    return ZIP_PATH


def main():
    prepare_output()

    writer = ExportWriter()

    writer.write("=" * 100 + "\n")
    writer.write("AUDITAI EXPORT\n")
    writer.write(f"PROJECT ROOT : {ROOT}\n")
    writer.write(f"DATE : {datetime.now()}\n")
    writer.write("=" * 100 + "\n\n")

    writer.write("PROJECT TREE\n")
    writer.write("=" * 100 + "\n\n")
    writer.write(build_tree())
    writer.write("\n\n")

    writer.write("PROJECT FILES CONTENT\n")
    writer.write("=" * 100 + "\n\n")

    exported_count = export_files(writer)
    parts = writer.part
    writer.close()

    manifest = create_manifest(exported_count, parts)
    zip_path = create_zip()

    print()
    print("=" * 60)
    print("EXPORT COMPLETED")
    print("=" * 60)
    print(f"Project root    : {ROOT}")
    print(f"Exported files  : {exported_count}")
    print(f"Parts generated : {parts}")
    print(f"Manifest        : {manifest}")
    print(f"ZIP generated   : {zip_path}")
    print("=" * 60)
    print()
    print("Tu peux maintenant m'envoyer ce fichier :")
    print(zip_path)
    print()


if __name__ == "__main__":
    main()