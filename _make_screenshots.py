"""Generate screen_joining.png and screen_stones.png."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

BG = "#F7F8F6"
CARD = "#FFFFFF"
BORDER = "#CDD6D0"
RED = "#A94730"
DARK = "#1C2823"
MID = "#53645B"
GREEN = "#2E7D52"
LIGHT_GREEN = "#E8F5EE"
AMBER = "#B45309"
LIGHT_AMBER = "#FEF3C7"
BLUE = "#1D4ED8"
LIGHT_BLUE = "#EFF6FF"

W, H = 900, 620


def font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf" if not bold else "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


# ── screen_joining.png ───────────────────────────────────────────
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# Header
d.rectangle([(0, 0), (W, 56)], fill=DARK)
d.text((24, 14), "White Stone", fill="white", font=font(22, bold=True))
d.text((W - 120, 18), "Create  Open", fill="#9CA3AF", font=font(16))

# Title
d.text((40, 80), "Joining — Family Vault", fill=DARK, font=font(20, bold=True))
d.text((40, 112), "Provide tesserae from at least 2 groups to open this Stone.", fill=MID, font=font(14))

# Group A card
rounded_rect(d, [(40, 148), (420, 310)], 12, fill=CARD, outline=BORDER, width=2)
d.text((60, 164), "Family  (2 of 3 needed)", fill=DARK, font=font(15, bold=True))
# progress bar bg
rounded_rect(d, [(60, 196), (400, 212)], 6, fill="#E5E7EB")
rounded_rect(d, [(60, 196), (230, 212)], 6, fill=AMBER)
d.text((60, 220), "1 of 2 tesserae  ·  not ready", fill=AMBER, font=font(13))
for i, (label, col) in enumerate([("shard1.txt ✓", GREEN), ("— missing —", "#9CA3AF"), ("— missing —", "#9CA3AF")]):
    rounded_rect(d, [(60, 244 + i * 20), (400, 260 + i * 20)], 4,
                 fill=LIGHT_GREEN if col == GREEN else "#F9FAFB", outline=BORDER)
    d.text((68, 246 + i * 20), label, fill=col, font=font(12))

# Group B card
rounded_rect(d, [(460, 148), (860, 310)], 12, fill=CARD, outline=GREEN, width=2)
d.text((480, 164), "Lawyer  (1 of 1 needed)", fill=DARK, font=font(15, bold=True))
rounded_rect(d, [(480, 196), (840, 212)], 6, fill="#E5E7EB")
rounded_rect(d, [(480, 196), (840, 212)], 6, fill=GREEN)
d.text((480, 220), "1 of 1 tesserae  ·  ready ✓", fill=GREEN, font=font(13))
rounded_rect(d, [(480, 244), (840, 260)], 4, fill=LIGHT_GREEN, outline=BORDER)
d.text((488, 246), "lawyer-tessera.txt ✓", fill=GREEN, font=font(12))

# Overall status banner
rounded_rect(d, [(40, 330), (860, 376)], 10, fill=LIGHT_AMBER, outline=AMBER, width=1)
d.text((60, 344), "⚠  1 of 2 groups ready — add at least one more Family tessera to open.", fill=AMBER, font=font(14))

# Drop zone
rounded_rect(d, [(40, 396), (860, 460)], 10, fill="#F9FAFB", outline=BORDER, width=2)
d.text((340, 418), "Drop tessera files here", fill=MID, font=font(15))
d.text((360, 440), "or click to browse", fill="#9CA3AF", font=font(13))

# Reveal button (disabled)
rounded_rect(d, [(340, 480), (560, 516)], 8, fill="#D1D5DB")
d.text((378, 491), "Reveal secret", fill="#6B7280", font=font(15))

img.save(Path(__file__).parent / "screen_joining.png")
print("Saved screen_joining.png")


# ── screen_stones.png ────────────────────────────────────────────
img2 = Image.new("RGB", (W, H), BG)
d2 = ImageDraw.Draw(img2)

# Header
d2.rectangle([(0, 0), (W, 56)], fill=DARK)
d2.text((24, 14), "White Stone", fill="white", font=font(22, bold=True))
d2.text((W - 120, 18), "Create  Open", fill="#9CA3AF", font=font(16))

# Title
d2.text((40, 80), "Create a Stone", fill=DARK, font=font(20, bold=True))
d2.text((40, 112), "Seal a secret and distribute tesserae to your Keepers.", fill=MID, font=font(14))

# Stone name field
d2.text((40, 152), "Stone name", fill=MID, font=font(13))
rounded_rect(d2, [(40, 172), (860, 204)], 6, fill=CARD, outline=BORDER, width=2)
d2.text((56, 181), "Family Vault", fill=DARK, font=font(14))

# Secret field
d2.text((40, 220), "Secret to protect", fill=MID, font=font(13))
rounded_rect(d2, [(40, 240), (860, 272)], 6, fill=CARD, outline=BORDER, width=2)
d2.text((56, 249), "● ● ● ● ● ● ● ● ● ● ● ●", fill="#9CA3AF", font=font(14))

# Keepers row
d2.text((40, 292), "Number of Keepers", fill=MID, font=font(13))
rounded_rect(d2, [(40, 312), (200, 344)], 6, fill=CARD, outline=BORDER, width=2)
d2.text((56, 321), "5  ▾", fill=DARK, font=font(14))

d2.text((240, 292), "Keepers needed to open", fill=MID, font=font(13))
rounded_rect(d2, [(240, 312), (420, 344)], 6, fill=CARD, outline=BORDER, width=2)
d2.text((256, 321), "3  ▾", fill=DARK, font=font(14))

# Keeper name chips
d2.text((40, 364), "Name the Keepers", fill=MID, font=font(13))
names = ["Alice", "Bob", "Carol", "Dave", "Eve"]
for i, name_text in enumerate(names):
    x = 40 + i * 168
    rounded_rect(d2, [(x, 384), (x + 156, 416)], 6, fill=CARD, outline=BORDER, width=2)
    d2.text((x + 12, 393), name_text, fill=DARK, font=font(14))

# Seal button
rounded_rect(d2, [(340, 448), (560, 488)], 8, fill=RED)
d2.text((376, 459), "🔒  Seal Stone", fill="white", font=font(16, bold=True))

# Caption
d2.text((40, 508), "Secret and Keeper material are handled by this local app process. Nothing is uploaded.", fill="#9CA3AF", font=font(12))

# Warning note
rounded_rect(d2, [(40, 536), (860, 572)], 8, fill=LIGHT_BLUE, outline="#BFDBFE", width=1)
d2.text((60, 549), "ℹ  Keep the Stone file separate from the Keeper cards after sealing.", fill=BLUE, font=font(13))

img2.save(Path(__file__).parent / "screen_stones.png")
print("Saved screen_stones.png")
