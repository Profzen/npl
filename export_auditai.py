import os
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(**file**).parent

MAX_SIZE = 20 * 1024 * 1024

EXCLUDED_DIRS = {
".git",
".next",
"node_modules",
"**pycache**",
"venv",
".venv",
"dist",
"build",
".cache"
}

EXCLUDED_EXTENSIONS = {
".gguf",
".safetensors",
".onnx",
".pt",
".pth",
".ckpt",
".dll",
".exe"
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
".jinja"
}

def should_skip(path):

```
for part in path.parts:

    if part in EXCLUDED_DIRS:
        return True

    if part.startswith("checkpoint-"):
        return True

if path.suffix.lower() in EXCLUDED_EXTENSIONS:
    return True

return False
```

def notebook_to_text(path):

```
try:

    with open(path, "r", encoding="utf-8") as f:
        notebook = json.load(f)

    content = []

    for i, cell in enumerate(
            notebook.get("cells", []), start=1):

        content.append(
            f"\n### CELL {i}\n"
        )

        content.append(
            f"TYPE: {cell.get('cell_type')}\n\n"
        )

        source = cell.get("source", [])

        content.extend(source)

        content.append("\n")

    return "".join(content)

except Exception as e:

    return f"[NOTEBOOK ERROR] {e}"
```

class ExportWriter:

```
def __init__(self):

    self.part = 1
    self.current_size = 0

    self.file = open(
        ROOT / f"auditai_export_part_{self.part}.txt",
        "w",
        encoding="utf-8"
    )

def write(self, text):

    encoded = text.encode("utf-8")

    if self.current_size + len(encoded) > MAX_SIZE:

        self.file.close()

        self.part += 1

        self.current_size = 0

        self.file = open(
            ROOT /
            f"auditai_export_part_{self.part}.txt",
            "w",
            encoding="utf-8"
        )

    self.file.write(text)

    self.current_size += len(encoded)

def close(self):
    self.file.close()
```

def build_tree():

```
lines = []

for root, dirs, files in os.walk(ROOT):

    dirs[:] = [
        d for d in dirs
        if d not in EXCLUDED_DIRS
    ]

    level = root.replace(
        str(ROOT),
        ""
    ).count(os.sep)

    indent = "    " * level

    lines.append(
        f"{indent}{os.path.basename(root)}/"
    )

    for file in files:

        path = Path(root) / file

        if should_skip(path):
            continue

        lines.append(
            f"{indent}    {file}"
        )

return "\n".join(lines)
```

def export_files(writer):

```
exported = 0

for root, dirs, files in os.walk(ROOT):

    dirs[:] = [
        d for d in dirs
        if d not in EXCLUDED_DIRS
    ]

    for file in files:

        path = Path(root) / file

        if should_skip(path):
            continue

        if path.name.startswith(
                "auditai_export_part_"):
            continue

        if path.name == "auditai_manifest.txt":
            continue

        if path.suffix.lower() \
                not in TEXT_EXTENSIONS:
            continue

        exported += 1

        writer.write(
            "\n\n" +
            "=" * 100 +
            "\n"
        )

        writer.write(
            f"FILE : {path.relative_to(ROOT)}\n"
        )

        writer.write(
            "=" * 100 +
            "\n\n"
        )

        try:

            if path.suffix.lower() == ".ipynb":

                content = notebook_to_text(path)

            else:

                content = path.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

            writer.write(content)

        except Exception as e:

            writer.write(
                f"[READ ERROR] {e}"
            )

return exported
```

def main():

```
manifest = ROOT / "auditai_manifest.txt"

writer = ExportWriter()

writer.write(
    "=" * 100 + "\n"
)

writer.write(
    "AUDITAI EXPORT V3\n"
)

writer.write(
    f"DATE : {datetime.now()}\n"
)

writer.write(
    "=" * 100 + "\n\n"
)

tree = build_tree()

writer.write(
    "PROJECT TREE\n\n"
)

writer.write(tree)

writer.write("\n\n")

exported_count = export_files(writer)

parts = writer.part

writer.close()

with open(
        manifest,
        "w",
        encoding="utf-8") as f:

    f.write(
        "AUDITAI MANIFEST\n"
    )

    f.write(
        "=" * 60 + "\n\n"
    )

    f.write(
        f"Generated : "
        f"{datetime.now()}\n\n"
    )

    f.write(
        f"Exported files : "
        f"{exported_count}\n"
    )

    f.write(
        f"Export parts : "
        f"{parts}\n\n"
    )

    for i in range(1, parts + 1):

        f.write(
            f"auditai_export_part_{i}.txt\n"
        )

print()
print("=" * 60)
print("EXPORT COMPLETED")
print("=" * 60)
print(f"Parts generated : {parts}")
print("=" * 60)
```

if **name** == "**main**":
main()
