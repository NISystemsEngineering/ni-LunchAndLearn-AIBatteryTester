"""Styled QR code for the repo: NI theme colours, battery icon in the centre.
Writes <out>.png (print resolution) and <out>.svg from the same geometry."""
import sys, os
ENV=os.environ.get
import segno
from PIL import Image, ImageDraw

URL = "https://github.com/NISystemsEngineering/ni-LunchAndLearn-AIBatteryTester"
OUT = sys.argv[1]

NAVY, BLUE, GREEN, WHITE = "#1B243C", "#004B8D", "#00AD7C", "#FFFFFF"  # deck theme "Connect 25"

qr = segno.make(URL, error="h", micro=False, boost_error=False)
m = [[bool(v) for v in row] for row in qr.matrix]
n = len(m)
B = 4                      # quiet zone, modules
W = n + 2 * B              # total size, modules

# Centre clear zone (whole modules) for the battery: 13 wide x 9 high
cx = n // 2
CL = dict(c0=cx - 6, c1=cx + 6, r0=cx - 4, r1=cx + 4)

def is_finder(r, c):
    return (r < 7 and c < 7) or (r < 7 and c >= n - 7) or (r >= n - 7 and c < 7)

def in_clear(r, c):
    return ENV("CLEAR","1")=="1" and CL["r0"] <= r <= CL["r1"] and CL["c0"] <= c <= CL["c1"]

# ---- geometry as a list of shapes, in module units --------------------------
# ("rrect", x, y, w, h, radius, fill) | ("poly", [(x,y),...], fill, stroke, sw)
shapes = []
DOT, DR = float(ENV("DOT","0.88")), float(ENV("DR","0.32"))
for r in range(n):
    for c in range(n):
        if m[r][c] and not is_finder(r, c) and not in_clear(r, c):
            off = (1 - DOT) / 2
            shapes.append(("rrect", B + c + off, B + r + off, DOT, DOT, DR, "grad"))

for (fr, fc) in [(0, 0), (0, n - 7), (n - 7, 0)]:
    x, y = B + fc, B + fr
    FR=float(ENV("FR","0"))
    shapes.append(("rrect", x, y, 7, 7, 2.0*FR, "grad"))
    shapes.append(("rrect", x + 1, y + 1, 5, 5, 1.3*FR, WHITE))
    shapes.append(("rrect", x + 2, y + 2, 3, 3, 0.9*FR, ENV("EYE", GREEN)))

if ENV("CLEAR","1")!="1":
    shapes=[x for x in shapes]
# Battery in the clear zone
x0, y0 = B + CL["c0"], B + CL["r0"]
x1, y1 = B + CL["c1"] + 1, B + CL["r1"] + 1
shapes.append(("rrect", x0, y0, x1 - x0, y1 - y0, 1.6, WHITE))
bx0, by0, bx1, by1 = x0 + 1.1, y0 + 1.5, x1 - 2.1, y1 - 1.5     # body
SW = 0.75
shapes.append(("rrect", bx0, by0, bx1 - bx0, by1 - by0, 1.1, NAVY))
shapes.append(("rrect", bx0 + SW, by0 + SW, bx1 - bx0 - 2 * SW, by1 - by0 - 2 * SW, 0.55, WHITE))
cap_h = (by1 - by0) * 0.42
shapes.append(("rrect", bx1 - 0.2, (by0 + by1 - cap_h) / 2, 1.1, cap_h, 0.35, NAVY))
ix0, iy0, ix1, iy1 = bx0 + SW + 0.45, by0 + SW + 0.45, bx1 - SW - 0.45, by1 - SW - 0.45
GAP, NB = 0.35, 4
bw = (ix1 - ix0 - GAP * (NB - 1)) / NB
for i in range(NB):
    shapes.append(("rrect", ix0 + i * (bw + GAP), iy0, bw, iy1 - iy0, 0.25, GREEN))
# Lightning bolt over the bars
mx, my, s = (ix0 + ix1) / 2, (iy0 + iy1) / 2, (iy1 - iy0) / 2 + 0.55
bolt = [(0.30, -1.0), (-0.55, 0.12), (-0.02, 0.12), (-0.30, 1.0), (0.55, -0.12), (0.02, -0.12)]
shapes.append(("poly", [(mx + px * s, my + py * s) for px, py in bolt], WHITE, NAVY, 0.22))

# ---- SVG ---------------------------------------------------------------------
def f(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {W}" width="{W * 10}" height="{W * 10}">',
       f'<defs><linearGradient id="g" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{W}" y2="{W}">'
       f'<stop offset="0" stop-color="{NAVY}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient></defs>',
       f'<rect width="{W}" height="{W}" fill="{WHITE}"/>']
for sh in shapes:
    if sh[0] == "rrect":
        _, x, y, w, h, rad, fill = sh
        fill = "url(#g)" if fill == "grad" else fill
        svg.append(f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" rx="{f(rad)}" fill="{fill}"/>')
    else:
        _, pts, fill, stroke, sw = sh
        p = " ".join(f"{f(a)},{f(b)}" for a, b in pts)
        svg.append(f'<polygon points="{p}" fill="{fill}" stroke="{stroke}" stroke-width="{f(sw)}" stroke-linejoin="round"/>')
svg.append("</svg>")
open(OUT + ".svg", "w", encoding="utf-8").write("\n".join(svg))

# ---- PNG (drawn at 2x, downsampled for anti-aliasing) --------------------------
PX = 48                       # px per module in the final PNG
S = PX * 2
size = W * S
img = Image.new("RGB", (size, size), WHITE)

grad = Image.new("RGB", (size, size))
gd = ImageDraw.Draw(grad)
c_a = tuple(int(NAVY[i:i + 2], 16) for i in (1, 3, 5))
c_b = tuple(int(BLUE[i:i + 2], 16) for i in (1, 3, 5))
for k in range(2 * size):     # diagonal bands
    t = k / (2 * size - 1)
    col = tuple(round(a + (b - a) * t) for a, b in zip(c_a, c_b))
    gd.line([(k, 0), (0, k)], fill=col, width=2)

d = ImageDraw.Draw(img)
gmask = None                  # gradient shapes are batched into one mask, in drawing order

def flush():
    global gmask
    if gmask is not None:
        img.paste(grad, (0, 0), gmask)
        gmask = None

for sh in shapes:
    if sh[0] == "rrect":
        _, x, y, w, h, rad, fill = sh
        box = [x * S, y * S, (x + w) * S - 1, (y + h) * S - 1]
        if fill == "grad":
            if gmask is None:
                gmask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(gmask).rounded_rectangle(box, radius=rad * S, fill=255)
            continue
        flush()
        d.rounded_rectangle(box, radius=rad * S, fill=fill)
    else:
        flush()
        _, pts, fill, stroke, sw = sh
        P = [(a * S, b * S) for a, b in pts]
        d.polygon(P, fill=fill)
        d.line(P + [P[0], P[1]], fill=stroke, width=round(sw * S), joint="curve")
flush()

img = img.resize((W * PX, W * PX), Image.LANCZOS)
img.save(OUT + ".png", dpi=(600, 600))
print(f"version {qr.version}, error {qr.error}, {n}x{n} modules, PNG {W * PX}px")
