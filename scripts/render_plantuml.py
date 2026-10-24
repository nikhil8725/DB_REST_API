import os
import sys
import zlib
import urllib.request
from pathlib import Path


def encode_plantuml(text: str) -> str:
    """PlantUML standard compression encoding (deflate + 64-char ascii mapping)."""
    zlib_compressed = zlib.compress(text.encode("utf-8"))[2:-4]
    mapping = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    res = []
    pad = len(zlib_compressed) % 3
    data = zlib_compressed + b"\x00" * (3 - pad if pad else 0)
    for i in range(0, len(zlib_compressed), 3):
        b1, b2, b3 = data[i], data[i + 1], data[i + 2]
        res.append(mapping[b1 >> 2])
        res.append(mapping[((b1 & 0x3) << 4) | (b2 >> 4)])
        res.append(mapping[((b2 & 0xF) << 2) | (b3 >> 6)])
        res.append(mapping[b3 & 0x3F])
    if pad == 1:
        res = res[:-2]
    elif pad == 2:
        res = res[:-1]
    return "".join(res)


def main():
    root_dir = Path(__file__).resolve().parent.parent
    diagrams_dir = root_dir / "docs" / "diagrams"
    output_dir = diagrams_dir / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    puml_files = sorted(diagrams_dir.glob("*.puml"))
    if not puml_files:
        print(f"No .puml files found in {diagrams_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Found {len(puml_files)} PlantUML diagram(s) to render...")

    headers = {"User-Agent": "Mozilla/5.0 (compatible; PlantUMLRenderer/1.0)"}
    
    try:
        import certifi
        import ssl
        ssl_context = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        import ssl
        ssl_context = ssl._create_unverified_context()

    for puml_file in puml_files:
        name = puml_file.stem
        print(f"\n[*] Processing '{name}' ({puml_file.name})...")
        content = puml_file.read_text(encoding="utf-8")
        encoded = encode_plantuml(content)

        # 1. Fetch SVG
        svg_url = f"https://www.plantuml.com/plantuml/svg/{encoded}"
        svg_path = output_dir / f"{name}.svg"
        print(f"    -> Fetching SVG from {svg_url[:60]}...")
        req = urllib.request.Request(svg_url, headers=headers)
        with urllib.request.urlopen(req, context=ssl_context, timeout=30) as resp:
            svg_data = resp.read()
            svg_path.write_bytes(svg_data)
        print(f"    [OK] Saved SVG to {svg_path} ({len(svg_data)} bytes)")

        # 2. Fetch PNG
        png_url = f"https://www.plantuml.com/plantuml/png/{encoded}"
        png_path = output_dir / f"{name}.png"
        print(f"    -> Fetching PNG from {png_url[:60]}...")
        req = urllib.request.Request(png_url, headers=headers)
        with urllib.request.urlopen(req, context=ssl_context, timeout=30) as resp:
            png_data = resp.read()
            png_path.write_bytes(png_data)
        print(f"    [OK] Saved PNG to {png_path} ({len(png_data)} bytes)")

    print("\n[OK] All PlantUML diagrams rendered successfully to docs/diagrams/images/!")


if __name__ == "__main__":
    main()
