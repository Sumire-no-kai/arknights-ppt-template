#!/usr/bin/env python3
"""Render every background and element of the template into ../assets."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inklib import *  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
os.makedirs(OUT, exist_ok=True)
CAST = (0.83, 0.56)
PX = W / 13.333  # pixels per slide inch


def inch(x, y):
    return (int(x * PX), int(y * PX))


FIG = figure_layers()


def place_figure(img, x, y, height, cast=(0.86, 0.5), stretch=2.7, tone=0.34):
    f = resize_rgba(FIG, height)
    img = cast_figure_shadow(img, f, x, y, cast=cast, stretch=stretch, tone=tone)
    return paste_rgba(img, f, x, y), f


def corner(img, seed=5, w=820, h=500, margin=0.42):
    ic = ink_corner(w, h, seed, margin)
    return paste_rgba(img, ic, W - w, H - h)


def smear(img, box, color, seed, strength=0.2):
    """Faint rust wash behind a display title; still reads as texture when text changes."""
    x0, y0, x1, y1 = box
    yy, xx = np.mgrid[0:H, 0:W].astype("f4")
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    d = 1 - np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    n = fbm(H, W, 230, 6, seed)
    s = streaks(H, W, -4, 360, 22, 4, seed + 1)
    s = warp(s, (n - 0.5) * 60, (n - 0.5) * 60)
    m = sstep(0.0, 0.62, d + (n - 0.5) * 0.85) * (0.62 + 0.38 * sstep(0.3, 0.8, s))
    return over(img, color, np.clip(m, 0, 1) * strength)


def spatter(img, box, seed, count=46, color=INK):
    """Sparse ink flicks gathered towards one end of the title."""
    r = np.random.default_rng(seed)
    x0, y0, x1, y1 = box
    im, d = canvas_mask()
    for _ in range(count):
        x = x1 - (x1 - x0) * r.random() ** 1.7
        y = r.uniform(y0, y1)
        s = abs(r.normal(0, 1.5)) + 0.5
        d.ellipse([(x - s) * SS, (y - s) * SS, (x + s) * SS, (y + s) * SS], fill=255)
    return over(img, color, down(im) * 0.7)


def stake(img, x, y, seed=8):
    """Small snow-capped marker with a sprig of green and a very long shadow."""
    shadow, d = canvas_mask()
    thick_line(d, (x, y + 8), (x + CAST[0] * 460, y + 8 + CAST[1] * 460), 26, 3, fill=235)
    img = multiply(img, 0.42, ndi.gaussian_filter(down(shadow), 1.8) * 0.85)
    body, b = canvas_mask()
    b.polygon([(p * SS, q * SS) for p, q in [(x - 26, y + 12), (x - 19, y - 10), (x + 21, y - 12), (x + 28, y + 10), (x + 6, y + 18)]], fill=255)
    img = over(img, (0.82, 0.82, 0.8), roughen(down(body), seed, cell=6, amount=0.3, blur=0.6))
    leaf, l = canvas_mask()
    r = np.random.default_rng(seed)
    for _ in range(16):
        px, py = x + r.uniform(-40, 30), y + r.uniform(-20, 2)
        thick_line(l, (px, py), (px + r.uniform(-11, 13), py + r.uniform(-8, 6)), 5, 1.5)
    return over(img, (0.33, 0.42, 0.27), roughen(down(leaf), seed + 1, cell=4, amount=0.42, blur=0.5))


def scene_trees(img, bases, shadow=0.6, crown=True):
    for base, seed, scale in bases:
        img = draw_tree(img, base, seed, scale=scale, shadow=shadow, crown=crown)
    return img


def fin(img, name, count=650, q=88):
    img = flecks(img, seed=hash(name) % 1000 + 3, count=count)
    save_jpg(img, os.path.join(OUT, name + ".jpg"), q=q)
    print(name, flush=True)


# ---------------------------------------------------------------------------
def red_tail(img, fx, fy, k=1.0, seed=9):
    pts = [(fx + 72 * k, fy + 74 * k), (fx + 130 * k, fy + 86 * k), (fx + 200 * k, fy + 60 * k),
           (fx + 262 * k, fy + 70 * k), (fx + 350 * k, fy + 34 * k)]
    return draw_ribbon(img, pts, RED, seed, wmin=2, wmax=9, shadow=(6, 12), dryness=0.4)


def cover():
    img = snow(seed=11, corner_tone=0.1, drift=0.85)
    img = smear(img, (70, 640, 1560, 1290), (0.46, 0.25, 0.18), 41, 0.2)
    img = scene_trees(img, [((430, 300), 201, 1.0), ((900, 280), 212, 1.05), ((1500, 300), 223, 1.0)])
    img = draw_tree(img, (2150, -90), 234, scale=0.95, crown=False)  # shadow only: keeps the header clear
    img = draw_ribbon(img, [(70, 130), (280, 150), (418, 205), (680, 136), (895, 192), (1200, 120), (1490, 205), (1700, 150)], RUST, 5, shadow=(10, 8))
    img = draw_ribbon(img, [(1880, 236), (2040, 214), (2230, 232), (2400, 212), (W + 20, 236)], RUST, 6, shadow=(10, 8))
    fx, fy = 1648, 610
    img = footprints(img, [(1716, -10), (1708, 240), (1716, 460), (1710, fy + 34)], 7)
    img = stake(img, 1590, 975)
    img, _ = place_figure(img, fx, fy, 190)
    img = red_tail(img, fx, fy)
    # a thin sapling grows up through the end of the display title
    img = draw_tree(img, (1500, 1000), 247, scale=0.5, height=420, width=7, depth=4, shadow=0.34)
    img = spatter(img, (120, 690, 1450, 1210), 44)
    img = corner(img, seed=5, w=980, h=640, margin=0.40)
    fin(img, "bg_cover", 760)


def maps():
    node_sets = {
        "bg_map5": [(6.1, 6.3), (9.05, 5.25), (11.15, 4.35), (11.3, 2.72), (9.65, 1.5)],
        "bg_map4": [(6.1, 6.3), (9.1, 5.1), (11.2, 3.7), (10.1, 1.75)],
        "bg_map3": [(6.1, 6.3), (9.6, 4.5), (10.6, 2.2)],
    }
    for name, nodes in node_sets.items():
        img = snow(seed=21, corner_tone=0.1, drift=0.85)
        img = smear(img, (40, 830, 1040, 1340), (0.46, 0.25, 0.18), 51, 0.2)
        img = scene_trees(img, [((470, 300), 301, 0.95), ((1000, 262), 312, 1.0), ((1760, 246), 323, 0.9)], shadow=0.52)
        img = draw_tree(img, (2200, -90), 334, scale=0.95, shadow=0.52, crown=False)  # shadow only: keeps the header clear
        img = draw_ribbon(img, [(70, 120), (290, 150), (458, 205), (760, 136), (990, 176), (1200, 110), (1290, 122)], RUST, 15, shadow=(10, 8))
        img = draw_ribbon(img, [(1752, 226), (1950, 206), (2110, 226), (2300, 204), (W + 20, 230)], RUST, 16, shadow=(10, 8))
        # A faint trail threads the chapter nodes in reading order, from the figure outwards.
        fx, fy = 1216, 650
        img = footprints(img, [(1282, -10), (1272, 240), (1282, 460), (fx + 62, fy + 28)], 18)
        route = [(fx + 70, fy + 190)] + [inch(*n) for n in nodes]
        img = footprints(img, route, 19, strength=0.42)
        img = stake(img, 1060, 930, 9)
        img, _ = place_figure(img, fx, fy, 172)
        img = red_tail(img, fx, fy, 0.9, 12)
        img = spatter(img, (70, 880, 980, 1290), 54, count=34)
        img = corner(img, seed=25, w=900, h=560, margin=0.40)
        fin(img, name, 700)


def content():
    img = snow(seed=33, drift=0.42)
    # Only the cast shadow enters the frame, so the header at top right stays clean.
    img = draw_tree(img, (1560, -70), 411, scale=0.95, shadow=0.24, crown=False)
    img = footprints(img, [(2424, 190), (2412, 400), (2422, 700), (2414, 1000)], 34, strength=0.5)
    img = corner(img, seed=35, w=640, h=450, margin=0.30)
    fin(img, "bg_content", 450)


def section():
    img = snow(seed=37, drift=0.7, corner_tone=0.04)
    img = draw_tree(img, (250, 210), 421, scale=0.8, shadow=0.42)
    fx, fy = 470, 800
    img = footprints(img, [(540, -10), (526, 330), (536, 620), (530, fy + 34)], 38)
    img, _ = place_figure(img, fx, fy, 178, cast=(0.82, 0.57), stretch=1.7)
    img = draw_ribbon(img, [(fx + 66, fy + 72), (fx + 120, fy + 78), (fx + 190, fy + 60), (fx + 270, fy + 74), (fx + 330, fy + 60)], RED, 39, wmin=2, wmax=9, dryness=0.4, shadow=(6, 12))
    ink = ink_field(W, H, 40, lambda x, y: (x * 1.12 - y * 0.1 - 0.335) * 0.8, noise=0.1)
    img = flecks(img, seed=30, count=300)
    img = paste_rgba(img, ink, 0, 0)
    save_jpg(img, os.path.join(OUT, "bg_section.jpg"), q=88)
    print("bg_section", flush=True)


def twocol():
    img = snow(seed=43, drift=0.4)
    img = fence(img, 1270, 44, ytop=-20, ybot=H + 20)
    img = draw_ribbon(img, [(1272, 262), (1360, 300), (1450, 268), (1540, 286), (1700, 226)], RED, 45, wmin=2.5, wmax=11, dryness=0.5, shadow=(8, 14))
    img = corner(img, seed=46, w=640, h=450, margin=0.30)
    fin(img, "bg_twocol", 380)


def image_page():
    img = snow(seed=47, drift=0.48)
    img = draw_ribbon(img, [(1410, 1278), (1620, 1244), (1800, 1270), (1990, 1240), (2180, 1262)], RUST, 48, shadow=(10, 8))
    img = corner(img, seed=49, w=640, h=450, margin=0.30)
    fin(img, "bg_image", 420)


def cards():
    img = snow(seed=53, drift=0.5)
    # The cord crosses below the title block and passes behind the top of the notes.
    img = draw_tree(img, (-160, -60), 441, scale=0.8, shadow=0.2, crown=False)
    img = draw_ribbon(img, [(-20, 372), (560, 408), (1000, 432), (1400, 434), (1860, 410), (W + 20, 336)], RUST, 54, wmin=3, wmax=11, shadow=(10, 12))
    img = corner(img, seed=55, w=640, h=450, margin=0.30)
    fin(img, "bg_cards", 420)


def timeline():
    img = snow(seed=57, drift=0.45)
    posts = [0.74 + 2.38 * i for i in range(5)]
    y0 = int(3.62 * PX)
    shadow, ds = canvas_mask()
    stick, dt = canvas_mask()
    r = np.random.default_rng(58)
    for p in posts:
        x = int(p * PX)
        thick_line(ds, (x, y0 + 58), (x + 214, y0 + 58 + 118), 13, 2.5, fill=225)
        px, py = x + r.normal(0, 2), y0 - 66
        for k in range(5):
            qx, qy = x + r.normal(0, 3), y0 - 66 + 124 * (k + 1) / 5
            thick_line(dt, (px, py), (qx, qy), r.uniform(9, 14), r.uniform(8, 13))
            if r.random() < 0.5:
                s = r.choice([-1, 1])
                thick_line(dt, (qx, qy), (qx + s * r.uniform(7, 16), qy - r.uniform(6, 20)), 5, 1.5)
            px, py = qx, qy
    img = multiply(img, 0.5, ndi.gaussian_filter(down(shadow), 1.6) * 0.8)
    pts = [(-20, y0 + 6)]
    for i, p in enumerate(posts):
        pts.append((int(p * PX), y0 - 16 + (i % 2) * 8))
        pts.append((int((p + 1.19) * PX), y0 + (10 if i % 2 else 18)))
    pts[-1] = (W + 20, y0 - 6)
    img = draw_ribbon(img, pts, RED, 59, wmin=3, wmax=11, dryness=0.5, shadow=(7, 15))
    img = over(img, INK * 1.05, roughen(down(stick), 60, cell=7, amount=0.42, blur=0.8))
    img = corner(img, seed=61, w=640, h=450, margin=0.30)
    fin(img, "bg_timeline", 400)


def data():
    img = snow(seed=63, drift=0.38)
    img = draw_tree(img, (2460, 40), 461, scale=0.7, shadow=0.2, crown=False)
    img = corner(img, seed=64, w=640, h=450, margin=0.30)
    fin(img, "bg_data", 380)


def quote():
    img = snow(seed=67, drift=0.62, corner_tone=0.05)
    img = draw_tree(img, (2130, 720), 471, scale=0.98, width=14, shadow=0.42, height=640)
    img = draw_ribbon(img, [(1790, 500), (1930, 560), (2030, 556), (2108, 590), (2300, 500), (2560, 560)], RUST, 68, wmin=3, wmax=12, shadow=(10, 12))
    img = corner(img, seed=69, w=640, h=450, margin=0.30)
    fin(img, "bg_quote", 520)


def credits_page():
    img = snow(seed=73, drift=0.32, base=0.93)
    fx, fy = 700, 628
    img = footprints(img, [(824, -10), (812, 220), (822, 450), (808, fy + 20)], 74, gap=30, size=(6.5, 19), offset=10, strength=0.5)
    img = fence(img, 1130, 75, thick=14)
    # the long shadow runs through the fence and thins to a thread that reaches the names
    f = resize_rgba(FIG, 292)
    img = cast_figure_shadow(img, f, fx, fy, cast=(0.985, 0.16), stretch=2.3, tone=0.46, length_fade=False)
    thread, d = canvas_mask()
    sp = catmull([(1320, 985), (1420, 1006), (1490, 992), (1538, 930)])
    for i in range(len(sp) - 1):
        t = i / len(sp)
        thick_line(d, sp[i], sp[i + 1], 11 * (1 - t) + 1.4, 11 * (1 - (i + 1) / len(sp)) + 1.4, fill=210)
    img = multiply(img, 0.46, ndi.gaussian_filter(down(thread), 1.3) * 0.86)
    img = paste_rgba(img, f, fx, fy)
    img = draw_ribbon(img, [(fx + 112, fy + 114), (fx + 200, fy + 92), (fx + 310, fy + 148), (fx + 430, fy + 130), (fx + 560, fy + 138), (fx + 620, fy + 100)], RED, 76, wmin=2.5, wmax=13, dryness=0.42)
    fin(img, "bg_credits", 330)


def ending():
    img = snow(seed=79, drift=0.68, corner_tone=0.06)
    img = fence(img, 1820, 80, ytop=-30, ybot=560, thick=13)
    img = draw_ribbon(img, [(1822, 410), (1960, 440), (2090, 400), (2240, 432), (2420, 378), (2560, 402)], RED, 81, wmin=2.5, wmax=12, dryness=0.5, shadow=(8, 14))
    img = footprints(img, [(1500, -10), (1490, 320), (1500, 640), (1560, 860), (1720, 1090), (1960, H + 20)], 82, strength=0.55)
    img = smear(img, (40, 430, 1400, 1000), (0.46, 0.25, 0.18), 83, 0.2)
    img = spatter(img, (80, 500, 1240, 980), 84, count=34)
    img = corner(img, seed=85, w=780, h=500, margin=0.34)
    fin(img, "bg_end", 620)


def blank():
    img = snow(seed=89, drift=0.3)
    img = corner(img, seed=90, w=640, h=450, margin=0.30)
    fin(img, "bg_blank", 330)


def textures():
    """Fills for live display text: alpha holes let the snow bite into the letters."""
    w, h = 1800, 620
    n = fbm(h, w, 60, 5, 301)
    s = streaks(h, w, -4, 260, 7, 4, 302)
    speck = fbm(h, w, 7, 3, 303)
    alpha = 1 - sstep(0.74, 0.84, s * 0.62 + n * 0.38) * 0.94
    alpha = alpha * (1 - sstep(0.86, 0.93, speck) * 0.85)
    tone = fbm(h, w, 200, 4, 304)
    for name, c0, c1 in (("tx_ink", (0.075, 0.07, 0.068), (0.21, 0.19, 0.18)),
                         ("tx_rust", (0.27, 0.13, 0.09), (0.50, 0.28, 0.19)),
                         ("tx_snow", (0.97, 0.965, 0.95), (0.78, 0.77, 0.75))):
        c0, c1 = np.asarray(c0, "f4"), np.asarray(c1, "f4")
        rgb = c0 + (c1 - c0) * tone[..., None]
        a = alpha if name != "tx_snow" else 1 - (1 - alpha) * 0.9
        save_png(np.dstack([rgb, a]), os.path.join(OUT, name + ".png"))


def sample_photo():
    w, h = 1440, 1262
    p = snow(seed=211, w=w, h=h, drift=1.25, base=0.80, flow=8)
    p = draw_tree(p, (520, 800), 233, scale=1.28, width=19, height=640, depth=5, stretch=1.7, shadow=0.62)
    p = draw_tree(p, (1190, 500), 239, scale=0.8, width=12, height=560, depth=5, stretch=2.1, shadow=0.5)
    p = draw_ribbon(p, [(0, 640), (220, 700), (440, 650), (500, 688), (760, 610), (1020, 640), (1160, 400)], RUST, 215, wmin=3, wmax=13, shadow=(10, 12))
    p = footprints(p, [(1010, h + 10), (1000, 950), (1050, 720), (1120, 540)], 216, gap=30, size=(7, 20), offset=11)
    yy, xx = np.mgrid[0:h, 0:w].astype("f4")
    rim = np.hypot(xx / w * 2 - 1, yy / h * 2 - 1)
    p = multiply(p, 0.52, sstep(0.55, 1.35, rim) * 0.85)
    p = flecks(p, seed=217, count=520)
    save_jpg(p, os.path.join(OUT, "sample_photo.jpg"), q=86)


def elements():
    save_png(resize_rgba(FIG, 900), os.path.join(OUT, "el_figure.png"))
    for kind, seed in [("town", 101), ("ember", 113), ("dawn", 127), ("chapel", 131), ("forest", 149)]:
        save_png(painting(kind, seed=seed), os.path.join(OUT, f"el_paint_{kind}.png"))
        print(kind, flush=True)
    save_png(burnt_paper(seed=2), os.path.join(OUT, "el_paper_tag.png"))
    save_png(burnt_paper(w=760, h=860, seed=7, emblem=False, stain=(0.45, 0.26, 0.2), burn_side="left"), os.path.join(OUT, "el_note_a.png"))
    save_png(burnt_paper(w=760, h=860, seed=12, emblem=False, stain=(0.40, 0.27, 0.21), burn_side="bottom"), os.path.join(OUT, "el_note_b.png"))
    save_png(burnt_paper(w=760, h=860, seed=19, emblem=False, stain=(0.46, 0.25, 0.19), burn_side="right"), os.path.join(OUT, "el_note_c.png"))
    save_png(ink_corner(980, 640, 5, 0.40), os.path.join(OUT, "el_ink_corner.png"))
    fw, fh = 300, 1300
    pale, dp = canvas_mask(fw, fh)
    dark, dd = canvas_mask(fw, fh)
    r = np.random.default_rng(95)
    for i, y in enumerate(range(16, fh - 16, 34)):
        s = 1 if i % 2 else -1
        x = fw / 2 + s * 15 + r.normal(0, 1.4)
        thick_line(dd, (x, y), (x, y + 21), 9, 6.5, fill=int(r.uniform(160, 255)))
        thick_line(dp, (x + 3, y + 1), (x + 3, y + 22), 7, 5)
    alpha_d = ndi.gaussian_filter(down(dark), 1.0) * 0.72
    alpha_p = ndi.gaussian_filter(down(pale), 1.2) * 0.65 * (1 - np.clip(alpha_d * 2, 0, 1))
    al = np.clip(alpha_d + alpha_p, 0, 1)
    tone_fp = (alpha_p * 1.0 + alpha_d * 0.3) / np.clip(al, 1e-3, 1)
    save_png(np.dstack([tone_fp, tone_fp, tone_fp, al]), os.path.join(OUT, "el_footprints.png"))
    # standalone ribbon on transparency for free placement
    rw, rh = 1400, 240
    rmask, _ = ribbon_mask([(30, 140), (300, 90), (560, 150), (820, 100), (1100, 140), (1370, 70)], 91, 3, 15, rw, rh)
    rough = roughen(rmask, 92, cell=4, amount=0.7, blur=0.7, soft=0.17)
    rough = rough * sstep(0.0, 0.3, streaks(rh, rw, 0, 150, 2.4, 3, 93))
    grain = streaks(rh, rw, 0, 70, 3, 3, 94)
    for name, color in (("el_ribbon_red", RED), ("el_ribbon_rust", RUST)):
        rgb = np.asarray(color, "f4")[None, None] * (0.58 + 0.62 * grain[..., None])
        save_png(np.dstack([np.clip(rgb, 0, 1), rough]), os.path.join(OUT, name + ".png"))


JOBS = dict(cover=cover, maps=maps, content=content, section=section, twocol=twocol,
            image=image_page, cards=cards, timeline=timeline, data=data, quote=quote,
            credits=credits_page, end=ending, blank=blank, elements=elements,
            textures=textures, photo=sample_photo)

if __name__ == "__main__":
    names = sys.argv[1:] or list(JOBS)
    for n in names:
        JOBS[n]()
