"""Vendor the web fonts locally.

Run once, at build time, on a machine with internet access. After that the app
serves the fonts itself and the browser never contacts a font CDN -- no
external request, no privacy leak, and the app works on an air-gapped box.

    python scripts/fetch_fonts.py

If it cannot reach the network, nothing breaks: app.css falls back to
'Noto Sans Hebrew' and the system stack, which is perfectly legible.
"""
import sys
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "fonts"

# Google Fonts serves the woff2 files directly; we mirror them rather than
# linking, so the running app has no outbound dependency.
FAMILIES = {
    "assistant-400": ("Assistant", 400),
    "assistant-600": ("Assistant", 600),
    "assistant-700": ("Assistant", 700),
    "frank-700": ("Frank Ruhl Libre", 700),
    "frank-900": ("Frank Ruhl Libre", 900),
    "plex-mono-500": ("IBM Plex Mono", 500),
}

# A modern UA is required or the CSS API returns legacy truetype rather than
# woff2.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _split_subsets(css: str) -> list[tuple[str, str]]:
    """Return [(subset_label, woff2_url)] in the order Google listed them."""
    out: list[tuple[str, str]] = []
    label = ""
    for line in css.splitlines():
        stripped = line.strip()
        if stripped.startswith("/*") and stripped.endswith("*/"):
            label = stripped.strip("/*").strip()
        elif "url(" in stripped and ".woff2" in stripped:
            out.append((label, stripped.split("url(")[1].split(")")[0]))
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0

    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as client:
        for name, (family, weight) in FAMILIES.items():
            target = OUT / f"{name}.woff2"
            if target.exists() and target.stat().st_size > 1000:
                print(f"  skip   {target.name} (already present)")
                written += 1
                continue
            try:
                css = client.get(
                    "https://fonts.googleapis.com/css2",
                    params={"family": f"{family}:wght@{weight}", "display": "swap"},
                ).text
                # Google emits one @font-face per subset, labelled by a
                # comment. Take the Hebrew subset, and the plain Latin one for
                # English mode and numerals.
                blocks = _split_subsets(css)
                wanted = [b for label, b in blocks if label in ("hebrew", "latin")]
                if not wanted:
                    print(f"  MISS   {name}: no hebrew/latin subset found")
                    continue

                for idx, url in enumerate(wanted):
                    dest = target if idx == 0 else OUT / f"{name}-latin.woff2"
                    blob = client.get(url).content
                    dest.write_bytes(blob)
                    print(f"  wrote  {dest.name}  {len(blob):,} bytes")
                written += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  MISS   {name}: {exc}")

    print(f"\n{written}/{len(FAMILIES)} fonts available in {OUT}")
    if written < len(FAMILIES):
        print("Missing fonts fall back to the system stack; nothing breaks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
