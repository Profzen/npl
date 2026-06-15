import json
d = json.load(open('tinyllama_oracle_v13_dataset.ipynb', encoding='utf-8'))
for i, c in enumerate(d['cells'], 1):
    src = ''.join(c.get('source', []))
    if not src.strip():
        continue
    first = src.splitlines()[0]
    # Identifier les blocs et constantes
    if 'BLOC' in src or 'bloc' in src[:200] or 'pairs_' in src[:500]:
        lines = src.splitlines()
        markers = [ln for ln in lines if 'BLOC' in ln or 'pairs_' in ln or 'blocA' in ln or 'blocB' in ln or 'blocC' in ln or 'blocD' in ln or 'blocE' in ln or 'blocF' in ln or 'TARGET' in ln]
        if markers:
            print(f"--- Cellule {i} ({len(src)} chars) ---")
            for m in markers[:15]:
                print(f"  {m.strip()[:100]}")
            print()
