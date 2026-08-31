"""Generate PWA icons.

The mark is an open loop: a ring with a gap. It is the whole product thesis in
one shape -- the arc does not meet itself, and neither does an unfinished task.
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

INK = (20, 16, 25, 255)
SURFACE = (30, 24, 38, 255)
ROSE = (255, 92, 122, 255)
AMBER = (245, 181, 68, 255)
JADE = (95, 211, 168, 255)

SS = 4  # supersample factor for smooth arcs


def draw_mark(size: int, padding_ratio: float = 0.20, bg: bool = True) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if bg:
        radius = int(s * 0.22)
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=INK)
        # A faint inner plate keeps the mark from floating on flat black.
        inset = int(s * 0.045)
        d.rounded_rectangle(
            [inset, inset, s - 1 - inset, s - 1 - inset],
            radius=int(radius * 0.85),
            outline=SURFACE,
            width=max(2, int(s * 0.008)),
        )

    pad = int(s * padding_ratio)
    box = [pad, pad, s - 1 - pad, s - 1 - pad]
    width = max(4, int(s * 0.085))

    # The open loop. The 62-degree gap is the unfinished part.
    d.arc(box, start=112, end=68, fill=ROSE, width=width)

    # Cap the arc ends so it reads as a drawn stroke, not a clipped circle.
    import math

    cx, cy = s / 2, s / 2
    r = (box[2] - box[0]) / 2
    for angle in (112, 68):
        rad = math.radians(angle)
        px, py = cx + r * math.cos(rad), cy + r * math.sin(rad)
        rr = width / 2
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=ROSE)

    # The dot sitting in the gap: the thing still waiting on you.
    dot_r = int(s * 0.082)
    dot_y = int(cy + r * 0.86)
    d.ellipse([cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r], fill=AMBER)

    # Inner tick: what it looks like when the loop finally closes.
    tick_w = max(3, int(s * 0.042))
    d.line(
        [(cx - r * 0.26, cy - r * 0.04), (cx - r * 0.06, cy + r * 0.16)],
        fill=JADE,
        width=tick_w,
        joint="curve",
    )
    d.line(
        [(cx - r * 0.06, cy + r * 0.16), (cx + r * 0.27, cy - r * 0.26)],
        fill=JADE,
        width=tick_w,
        joint="curve",
    )

    return img.resize((size, size), Image.LANCZOS)


def make_badge(size: int = 96) -> Image.Image:
    """Android badges are masked to a silhouette, so it must be solid white."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(s * 0.14)
    d.arc(
        [pad, pad, s - 1 - pad, s - 1 - pad],
        start=121,
        end=59,
        fill=(255, 255, 255, 255),
        width=max(4, int(s * 0.12)),
    )
    r = int(s * 0.1)
    d.ellipse([s / 2 - r, s * 0.80 - r, s / 2 + r, s * 0.80 + r], fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    draw_mark(192).save(OUT / "icon-192.png")
    draw_mark(512).save(OUT / "icon-512.png")
    # Maskable icons get aggressively cropped, so keep the mark well inside the
    # 80% safe zone.
    draw_mark(512, padding_ratio=0.30).save(OUT / "icon-maskable.png")
    draw_mark(180).save(OUT / "apple-touch-icon.png")
    draw_mark(32, padding_ratio=0.14).save(OUT / "favicon-32.png")
    make_badge().save(OUT / "badge.png")

    # An SVG for anywhere a crisp vector is nicer than a bitmap.
    (OUT / "icon.svg").write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="22" fill="#141019"/>
  <path d="M 34.5 76.5 A 30 30 0 1 1 65.5 76.5" fill="none" stroke="#FF5C7A"
        stroke-width="8.5" stroke-linecap="round"/>
  <circle cx="50" cy="82" r="7.5" fill="#F5B544"/>
  <path d="M 39.8 50.6 L 47.6 58.4 L 60.8 41" fill="none" stroke="#5FD3A8"
        stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
        encoding="utf-8",
    )
    print("icons written to", OUT)
    for f in sorted(OUT.iterdir()):
        print(" ", f.name, f.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
