"""Génère les variantes d'icônes pour le favicon Smart2D."""
from PIL import Image
from pathlib import Path

src_path = Path(__file__).parent / "smart2d_logo.jpeg"
out_dir = Path(__file__).parent

img = Image.open(src_path).convert("RGBA")

# Carré centré (recadre vers carré)
w, h = img.size
side = min(w, h)
left = (w - side) // 2
top = (h - side) // 2
img = img.crop((left, top, left + side, top + side))

# PNG haute qualité, plusieurs tailles
sizes = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "favicon-48x48.png": 48,
    "favicon-192x192.png": 192,
    "favicon-512x512.png": 512,
    "apple-touch-icon.png": 180,
}

for name, size in sizes.items():
    resized = img.resize((size, size), Image.LANCZOS)
    resized.save(out_dir / name, "PNG", optimize=True)
    print(f"  ✓ {name}")

# favicon.ico multi-résolution (16, 32, 48)
ico_sizes = [(16, 16), (32, 32), (48, 48)]
img.save(
    out_dir / "favicon.ico",
    format="ICO",
    sizes=ico_sizes,
)
print("  ✓ favicon.ico (16/32/48)")
print("Done.")
