from PIL import Image, ImageDraw
import math

SS = 1024  # supersample canvas
img = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

gold      = (255, 193, 46, 255)
gold_edge = (245, 158, 11, 255)
navy      = (20, 46, 82, 255)
navy_hi   = (37, 99, 164, 255)
frame     = (203, 213, 225, 255)
sky_note  = (255, 213, 110, 255)

# ---- Sun (upper) ----
cx, cy = SS // 2, int(0.375 * SS)
r_sun  = int(0.165 * SS)

# rays: rounded lines radiating out
n = 12
ray_w = int(0.030 * SS)
for i in range(n):
    a = (2 * math.pi / n) * i - math.pi / 2
    r1 = r_sun * 1.30
    r2 = r_sun * 1.72
    x1, y1 = cx + r1 * math.cos(a), cy + r1 * math.sin(a)
    x2, y2 = cx + r2 * math.cos(a), cy + r2 * math.sin(a)
    d.line([(x1, y1), (x2, y2)], fill=gold, width=ray_w)
    # rounded caps
    for (x, y) in ((x1, y1), (x2, y2)):
        d.ellipse([x - ray_w/2, y - ray_w/2, x + ray_w/2, y + ray_w/2], fill=gold)

# sun body with a subtle edge
d.ellipse([cx - r_sun, cy - r_sun, cx + r_sun, cy + r_sun], fill=gold, outline=gold_edge, width=int(0.012*SS))
# inner highlight
d.ellipse([cx - r_sun*0.6, cy - r_sun*0.75, cx + r_sun*0.55, cy + r_sun*0.35], fill=sky_note)
d.ellipse([cx - r_sun, cy - r_sun, cx + r_sun, cy + r_sun], outline=gold_edge, width=int(0.012*SS))

# ---- Solar panel (lower, in perspective) ----
# parallelogram: wider at bottom for a slight 3D tilt
top_y   = int(0.60 * SS)
bot_y   = int(0.90 * SS)
top_l, top_r = int(0.26 * SS), int(0.74 * SS)
bot_l, bot_r = int(0.17 * SS), int(0.83 * SS)
panel = [(top_l, top_y), (top_r, top_y), (bot_r, bot_y), (bot_l, bot_y)]
d.polygon(panel, fill=navy, outline=frame)

# grid lines (3 cols x 2 rows) matching the perspective
cols, rows = 3, 2
def lerp(a, b, t): return a + (b - a) * t
for c in range(1, cols):
    t = c / cols
    x_top = lerp(top_l, top_r, t)
    x_bot = lerp(bot_l, bot_r, t)
    d.line([(x_top, top_y), (x_bot, bot_y)], fill=navy_hi, width=int(0.012*SS))
for rr in range(1, rows):
    t = rr / rows
    y = lerp(top_y, bot_y, t)
    xl = lerp(top_l, bot_l, t)
    xr = lerp(top_r, bot_r, t)
    d.line([(xl, y), (xr, y)], fill=navy_hi, width=int(0.012*SS))
# frame outline on top
d.polygon(panel, outline=frame)
d.line([panel[0], panel[1]], fill=frame, width=int(0.014*SS))  # bright top edge

# ---- export sizes ----
def save(size, name):
    img.resize((size, size), Image.LANCZOS).save(name)

import os
os.makedirs("brands/custom_integrations/tesla_solar", exist_ok=True)
base = "brands/custom_integrations/tesla_solar"
save(256, f"{base}/icon.png")
save(512, f"{base}/icon@2x.png")
save(256, f"{base}/logo.png")
save(512, f"{base}/logo@2x.png")
# also a preview copy at repo root for the user to look at
save(512, "/tmp/tesla_solar_icon_preview.png")
print("icons written")
for f in os.listdir(base):
    print(" ", f)
