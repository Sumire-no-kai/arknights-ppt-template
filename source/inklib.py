"""Procedural snow-and-ink drawing primitives used by build_art.py."""
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

W, H = 2560, 1440
SS = 2  # supersample factor for vector masks

INK = np.array([0.105, 0.100, 0.098], "f4")
RED = np.array([0.690, 0.150, 0.125], "f4")
RUST = np.array([0.760, 0.400, 0.170], "f4")


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def vnoise(h, w, cell, seed, cell_y=None):
    """Bicubic value noise. cell / cell_y are the feature sizes in pixels."""
    r = np.random.default_rng(seed)
    cy = cell_y or cell
    gw, gh = max(3, int(w / cell) + 4), max(3, int(h / cy) + 4)
    g = r.random((gh, gw)).astype("f4")
    big = Image.fromarray(g).resize((int(gw * cell), int(gh * cy)), Image.BICUBIC)
    ox = int(r.integers(0, max(1, big.width - w)))
    oy = int(r.integers(0, max(1, big.height - h)))
    return np.asarray(big.crop((ox, oy, ox + w, oy + h)), "f4")


def fbm(h, w, cell, octaves=5, seed=0, gain=0.5, cell_y=None):
    out = np.zeros((h, w), "f4")
    amp, total = 1.0, 0.0
    for i in range(octaves):
        c = max(cell / 2 ** i, 1.5)
        cy = max(cell_y / 2 ** i, 1.5) if cell_y else None
        out += amp * vnoise(h, w, c, seed + 17 * i + 1, cy)
        total += amp
        amp *= gain
    out /= total
    lo, hi = np.percentile(out, [1, 99])
    return np.clip((out - lo) / (hi - lo), 0, 1)


def streaks(h, w, angle, long_cell, short_cell, octaves=4, seed=0):
    """Anisotropic noise rotated so the grain runs along `angle` degrees (y down)."""
    d = int(math.hypot(h, w)) + 8
    n = fbm(d, d, long_cell, octaves, seed, cell_y=short_cell)
    rot = Image.fromarray(n).rotate(-angle, resample=Image.BICUBIC)
    ox, oy = (d - w) // 2, (d - h) // 2
    return np.asarray(rot.crop((ox, oy, ox + w, oy + h)), "f4")


def warp(img, dx, dy, order=1):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype("f4")
    return ndi.map_coordinates(img, [yy + dy, xx + dx], order=order, mode="reflect")


def roughen(mask, seed=0, cell=7, amount=0.42, blur=0.9, soft=0.09):
    """Turn a clean mask into an ink mark: wobbly edge, thin parts break into dry-brush."""
    h, w = mask.shape
    m = ndi.gaussian_filter(mask, blur) if blur else mask
    n = fbm(h, w, cell, 3, seed)
    return sstep(0.5 - soft, 0.5 + soft, m + (n - 0.5) * amount)


def canvas_mask(w=W, h=H, ss=SS):
    im = Image.new("L", (w * ss, h * ss), 0)
    return im, ImageDraw.Draw(im)


def down(im, ss=SS):
    w, h = im.size
    return np.asarray(im.resize((w // ss, h // ss), Image.LANCZOS), "f4") / 255.0


def over(img, color, alpha):
    a = alpha[..., None]
    return img * (1 - a) + np.asarray(color, "f4") * a


def multiply(img, tone, alpha):
    """Darken towards `tone` (0 black..1 no change) with coverage alpha."""
    a = alpha[..., None]
    return img * (1 - a * (1 - tone))


def thick_line(d, p0, p1, w0, w1, fill=255, ss=SS):
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    a, b = w0 * ss / 2, w1 * ss / 2
    x0, y0, x1, y1 = x0 * ss, y0 * ss, x1 * ss, y1 * ss
    d.polygon(
        [(x0 + nx * a, y0 + ny * a), (x1 + nx * b, y1 + ny * b),
         (x1 - nx * b, y1 - ny * b), (x0 - nx * a, y0 - ny * a)],
        fill=fill,
    )
    if w1 * ss > 2.5:
        d.ellipse([x1 - b, y1 - b, x1 + b, y1 + b], fill=fill)


# ---------------------------------------------------------------- snow ------
def _stroke_layer(h, w, seed, count, wmin, wmax, lmin, lmax, wander=0.25, flow=None, ss=2):
    """Large wandering brush strokes on one low-res layer, returned 0..1."""
    r = np.random.default_rng(seed)
    im = Image.new("L", (w // ss, h // ss), 0)
    d = ImageDraw.Draw(im)
    field = fbm(h // ss, w // ss, 700 // ss, 3, seed + 5)
    base_ang = math.radians(flow if flow is not None else 18)
    for _ in range(count):
        x, y = r.uniform(-100, w + 100), r.uniform(-100, h + 100)
        L = r.uniform(lmin, lmax)
        wid = r.uniform(wmin, wmax)
        fill = int(r.uniform(90, 255))
        n = max(4, int(L / 40))
        ang = base_ang + r.normal(0, 0.35)
        px, py = x, y
        for i in range(n):
            fy = int(np.clip(py / ss, 0, field.shape[0] - 1))
            fx = int(np.clip(px / ss, 0, field.shape[1] - 1))
            ang += (field[fy, fx] - 0.5) * wander + r.normal(0, 0.03)
            qx, qy = px + math.cos(ang) * L / n, py + math.sin(ang) * L / n
            prof = math.sin(math.pi * (i + 1) / (n + 1)) ** 0.6
            ww = wid * prof
            nx, ny = -math.sin(ang), math.cos(ang)
            a, b = ww / ss / 2, ww / ss / 2
            d.polygon([(px / ss + nx * a, py / ss + ny * a), (qx / ss + nx * b, qy / ss + ny * b),
                       (qx / ss - nx * b, qy / ss - ny * b), (px / ss - nx * a, py / ss - ny * a)], fill=fill)
            d.ellipse([qx / ss - b, qy / ss - b, qx / ss + b, qy / ss + b], fill=fill)
            px, py = qx, qy
    return np.asarray(im.resize((w, h), Image.BICUBIC), "f4") / 255.0


def snow(seed=1, w=W, h=H, drift=1.0, base=0.945, corner_tone=0.0, flow=18):
    """Impasto snowfield: overlapping loaded-brush strokes lit from the upper left."""
    wash = fbm(h, w, 1100, 4, seed)
    img = base + (wash - 0.5) * 0.05

    broad = _stroke_layer(h, w, seed + 1, 130, 110, 340, 400, 1500, flow=flow)
    mid = _stroke_layer(h, w, seed + 2, 120, 34, 130, 220, 900, flow=flow + 8)
    fine = _stroke_layer(h, w, seed + 3, 60, 8, 22, 160, 620, flow=flow - 6)
    bristle = streaks(h, w, flow, 420, 13, 3, seed + 4)
    bristle = warp(bristle, (fbm(h, w, 420, 2, seed + 6) - 0.5) * 70, (fbm(h, w, 420, 2, seed + 7) - 0.5) * 70)
    # Patchy coverage leaves calm, smooth snow between the worked areas.
    cover = sstep(0.34, 0.68, fbm(h, w, 640, 3, seed + 8))

    height = (ndi.gaussian_filter(broad, 13) * 0.95 + ndi.gaussian_filter(mid, 7) * 0.7
              + ndi.gaussian_filter(fine, 2.5) * 0.3) * cover
    height = height * (0.93 + 0.14 * bristle)
    gy, gx = np.gradient(height)
    relief = gx * 0.72 + gy * 0.69  # light from the upper left, so far slopes darken
    img = img - np.clip(relief, 0, None) * 2.9 * drift + np.clip(-relief, 0, None) * 1.3 * drift

    # A little grey pooled in the hollows between strokes.
    hollow = ndi.gaussian_filter(height, 26) - ndi.gaussian_filter(height, 5)
    img = img - np.clip(hollow, 0, None) * 0.2 * drift

    if corner_tone:
        yy, xx = np.mgrid[0:h, 0:w].astype("f4")
        tr = np.clip((xx / w - 0.45) / 0.55, 0, 1) * np.clip(1 - yy / (h * 0.45), 0, 1)
        n = fbm(h, w, 500, 3, seed + 9)
        img = img - sstep(0.1, 1.0, tr + (n - 0.5) * 0.35) * corner_tone

    grain = fbm(h, w, 3, 2, seed + 40)
    img = img + (grain - 0.5) * 0.01
    img = np.clip(img, 0, 1)
    return np.repeat(img[..., None], 3, axis=2) * np.array([1.0, 0.998, 0.992], "f4")


def flecks(img, seed=3, count=900, wind=(1.0, 0.1)):
    """Blowing snow: short pale dashes plus a few grey specks."""
    r = np.random.default_rng(seed)
    h, w = img.shape[:2]
    pale, dp = canvas_mask(w, h)
    grey, dg = canvas_mask(w, h)
    for _ in range(count):
        x, y = r.uniform(0, w), r.uniform(0, h)
        L = r.uniform(2, 13)
        t = r.uniform(0.7, 2.3)
        thick_line(dp, (x, y), (x + L * wind[0], y + L * wind[1]), t, t * 0.5)
    for _ in range(count // 5):
        x, y = r.uniform(0, w), r.uniform(0, h)
        L = r.uniform(1, 5)
        thick_line(dg, (x, y), (x + L, y + L * 0.2), 1.3, 0.7)
    img = over(img, (1, 1, 1), ndi.gaussian_filter(down(pale), 0.5) * 0.85)
    img = multiply(img, 0.55, ndi.gaussian_filter(down(grey), 0.4) * 0.55)
    return img


# ---------------------------------------------------------------- trees -----
def gen_tree(seed, height=560, width=15, max_depth=5):
    """Bare winter tree as tapered segments in tree space (y = height above root)."""
    r = np.random.default_rng(seed)
    segs = []

    def grow(x, y, ang, L, w, d):
        n = max(3, int(L / 20))
        step = L / n
        wp = w
        for i in range(n):
            ang += r.normal(0, 0.075 + 0.035 * d)
            ang += (math.pi / 2 - ang) * 0.012
            nx, ny = x + math.cos(ang) * step, y + math.sin(ang) * step
            nw = w * (1 - 0.66 * (i + 1) / n)
            segs.append((x, y, nx, ny, wp, nw, d))
            if d < max_depth and i > 0 and r.random() < (0.2 if d < 2 else 0.27):
                s = r.choice([-1, 1])
                grow(nx, ny, ang + s * r.uniform(0.45, 1.05), L * r.uniform(0.45, 0.78),
                     nw * r.uniform(0.6, 0.85), d + 1)
            x, y, wp = nx, ny, nw
        if d < max_depth and (d < 3 or r.random() < 0.72):
            for s in (-1, 1):
                grow(x, y, ang + s * r.uniform(0.22, 0.62), L * r.uniform(0.58, 0.82),
                     wp * 0.8, d + 1)

    grow(0, 0, math.pi / 2 + r.normal(0, 0.04), height * 0.31, width, 0)
    return segs


def draw_tree(img, base, seed, scale=1.0, height=560, width=13, depth=5,
              lean=(-0.42, -0.91), cast=(0.83, 0.56), stretch=3.0, shadow=0.6, crown=True):
    """Top-down tree: short foreshortened ink trunk, long skewed cast shadow."""
    h, w = img.shape[:2]
    segs = gen_tree(seed, height, width, depth)
    bx, by = base
    ey = (lean[0] * scale, lean[1] * scale)
    ex = (-lean[1] * scale, lean[0] * scale)
    sy = (cast[0] * scale * stretch, cast[1] * scale * stretch)
    sx = (-cast[1] * scale * 1.2, cast[0] * scale * 1.2)
    vmax = max(s[3] for s in segs)
    depth_gain = {0: 1.0, 1: 0.92, 2: 0.78, 3: 0.62, 4: 0.48, 5: 0.32, 6: 0.0}

    near, dn = canvas_mask(w, h)
    far, df = canvas_mask(w, h)
    for x0, y0, x1, y1, w0, w1, d in segs:
        gain = depth_gain.get(d, 0.0)
        if gain == 0:
            continue
        p0 = (bx + x0 * sx[0] + y0 * sy[0], by + x0 * sx[1] + y0 * sy[1])
        p1 = (bx + x1 * sx[0] + y1 * sy[0], by + x1 * sx[1] + y1 * sy[1])
        fade = (1 - 0.8 * min(1, y1 / vmax)) * gain
        tgt = dn if y1 < vmax * 0.36 else df
        thick_line(tgt, p0, p1, max(w0 * 1.3, 1.2), max(w1 * 1.3, 0.9), fill=int(255 * fade))
    wob_x = (fbm(h, w, 90, 3, seed + 92) - 0.5) * 5
    wob_y = (fbm(h, w, 90, 3, seed + 93) - 0.5) * 5
    shade_n = warp(ndi.gaussian_filter(down(near), 1.3), wob_x, wob_y)
    shade_f = warp(ndi.gaussian_filter(down(far), 2.6), wob_x, wob_y)
    angle = math.degrees(math.atan2(cast[1], cast[0]))
    grain = streaks(h, w, angle, 240, 7, 3, seed + 90)
    a = np.maximum(shade_n, shade_f) * (0.86 + 0.26 * grain)
    img = multiply(img, 1 - shadow, np.clip(a, 0, 1))

    if not crown:
        return img
    trunk, dt = canvas_mask(w, h)
    twig, dw = canvas_mask(w, h)
    for x0, y0, x1, y1, w0, w1, d in segs:
        p0 = (bx + x0 * ex[0] + y0 * ey[0], by + x0 * ex[1] + y0 * ey[1])
        p1 = (bx + x1 * ex[0] + y1 * ey[0], by + x1 * ex[1] + y1 * ey[1])
        tgt = dt if d <= 1 else dw
        thick_line(tgt, p0, p1, max(w0, 1.2), max(w1, 0.9))
    m = roughen(down(trunk), seed + 91, cell=6, amount=0.36, blur=0.6)
    img = over(img, INK * 1.1, m)
    img = over(img, INK * 2.0, np.clip(ndi.gaussian_filter(down(twig), 0.5) * 1.08, 0, 1) * 0.9)
    return img


# ---------------------------------------------------------------- ribbon ----
def catmull(pts, n=40):
    pts = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = map(np.array, (pts[i - 1], pts[i], pts[i + 1], pts[i + 2]))
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(np.array(pts[-1], float))
    return np.array(out, float)


def ribbon_mask(pts, seed, wmin=2.5, wmax=11, w=W, h=H, taper_end=True, lumps=5):
    """Calligraphic ribbon: width swells and pinches irregularly along the spine."""
    r = np.random.default_rng(seed)
    sp = catmull(pts)
    n = len(sp)
    u = np.linspace(0, 1, n)
    ph = r.uniform(0, 6.28, lumps)
    fr = r.uniform(1.5, 7.5, lumps)
    wave = sum(np.sin(2 * np.pi * fr[i] * u + ph[i]) for i in range(lumps)) / lumps
    wave = np.clip(0.5 + 0.95 * wave, 0, 1) ** 1.6
    width = wmin + (wmax - wmin) * wave
    if taper_end:
        width *= np.minimum(1, (1 - u) * 7 + 0.1)
    im, d = canvas_mask(w, h)
    for i in range(n - 1):
        thick_line(d, sp[i], sp[i + 1], width[i], width[i + 1])
    return down(im), sp


def draw_ribbon(img, pts, color, seed, wmin=2.5, wmax=11, shadow=None, grain_angle=0.0, dryness=1.0):
    h, w = img.shape[:2]
    m, sp = ribbon_mask(pts, seed, wmin, wmax, w, h)
    if shadow is not None:
        sh = warp(m, np.full_like(m, -shadow[0]), np.full_like(m, -shadow[1]))
        img = multiply(img, 0.5, ndi.gaussian_filter(sh, 2.6) * 0.5)
    # Ragged edge, then long dry-brush gaps so the cloth looks worn rather than vector.
    rough = roughen(m, seed + 1, cell=4, amount=0.72, blur=0.7, soft=0.17)
    dry = streaks(h, w, grain_angle, 150, 2.4, 3, seed + 3)
    rough = rough * sstep(0.1 * dryness - 0.05, 0.42 * dryness, dry)
    g = streaks(h, w, grain_angle, 70, 3, 3, seed + 2)
    col = np.asarray(color, "f4")[None, None, :] * (0.58 + 0.62 * g[..., None])
    a = np.clip(rough, 0, 1)[..., None]
    return img * (1 - a) + col * a


# ---------------------------------------------------------------- footsteps -
def footprints(img, spine, seed, gap=26, offset=8, size=(5.0, 15.0), strength=0.6):
    """Alternating dents along a polyline; each has a dark bowl and bright lip."""
    r = np.random.default_rng(seed)
    h, w = img.shape[:2]
    sp = catmull(spine)
    seglen = np.hypot(*np.diff(sp, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seglen)])
    dark, dd = canvas_mask(w, h)
    lite, dl = canvas_mask(w, h)
    s, side = r.uniform(0, gap), 1
    while s < cum[-1]:
        i = min(np.searchsorted(cum, s), len(sp) - 2)
        p = sp[i]
        tx, ty = sp[i + 1] - sp[i]
        L = math.hypot(tx, ty) or 1
        tx, ty = tx / L, ty / L
        px, py = p[0] - ty * offset * side, p[1] + tx * offset * side
        px, py = px + r.normal(0, 0.8), py + r.normal(0, 1.2)
        a, b = size[0] * r.uniform(0.8, 1.2), size[1] * r.uniform(0.8, 1.2)
        if r.random() > 0.03:
            q0 = (px - tx * b / 2, py - ty * b / 2)
            q1 = (px + tx * b / 2, py + ty * b / 2)
            thick_line(dd, q0, q1, a, a * 0.7, fill=int(r.uniform(150, 255)))
            thick_line(dl, (q0[0] + 3, q0[1] + 2), (q1[0] + 3, q1[1] + 2), a * 0.7, a * 0.5)
        s += gap * r.uniform(0.88, 1.12)
        side = -side
    img = over(img, (1, 1, 1), ndi.gaussian_filter(down(lite), 1.1) * 0.75)
    img = multiply(img, 0.32, ndi.gaussian_filter(down(dark), 0.9) * strength)
    return img


# ---------------------------------------------------------------- figure ----
def _jag(p0, p1, n, amp, r, bias=0.0):
    """Tattered edge between two points: alternating spikes off the straight line."""
    x0, y0 = p0
    x1, y1 = p1
    L = math.hypot(x1 - x0, y1 - y0) or 1
    nx, ny = -(y1 - y0) / L, (x1 - x0) / L
    out = []
    for i in range(1, n):
        t = i / n
        k = (amp * r.uniform(0.35, 1.3) if i % 2 else -amp * r.uniform(0.0, 0.4)) + bias
        out.append((x0 + (x1 - x0) * t + nx * k + r.normal(0, 1.5),
                    y0 + (y1 - y0) * t + ny * k + r.normal(0, 1.5)))
    return out


def figure_layers(seed=4, ss=6):
    """Original small cloaked wanderer on a 400x600 grid. Returns an RGBA float array."""
    r = np.random.default_rng(seed)
    W0, H0 = 400, 600
    layers = []

    def poly(points, color):
        layers.append(([(x * ss, y * ss) for x, y in points], color))

    # long far wing of the cloak, slate-black feathers trailing left and down
    wing = [(182, 150), (150, 170)] + _jag((150, 170), (22, 300), 11, 12, r)
    wing += _jag((22, 300), (118, 412), 13, 30, r) + [(118, 412), (186, 320)]
    poly(wing, (0.135, 0.150, 0.190))
    wing2 = [(176, 186)] + _jag((176, 186), (62, 340), 9, 9, r) + _jag((62, 340), (146, 436), 10, 24, r) + [(146, 436), (192, 330)]
    poly(wing2, (0.085, 0.090, 0.112))
    # slim legs + boots behind the skirt
    poly([(186, 400), (203, 400), (199, 505), (205, 556), (180, 560), (179, 505)], (0.070, 0.068, 0.068))
    poly([(220, 396), (237, 396), (241, 488), (252, 538), (228, 544), (222, 488)], (0.070, 0.068, 0.068))
    poly([(181, 476), (199, 476), (198, 487), (180, 487)], (0.62, 0.13, 0.11))
    poly([(223, 462), (240, 462), (241, 473), (224, 473)], (0.62, 0.13, 0.11))
    # torn skirt: long narrow strips on the hem
    skirt = [(176, 262), (236, 262), (282, 336)]
    skirt += _jag((282, 336), (272, 428), 5, 18, r)
    skirt += _jag((272, 428), (138, 446), 15, 40, r)
    skirt += _jag((138, 446), (140, 330), 5, 13, r)
    poly(skirt, (0.055, 0.053, 0.055))
    # coat
    poly([(174, 152), (238, 152), (246, 208), (236, 282), (176, 282), (166, 208)], (0.080, 0.078, 0.080))
    # short right cape
    cape = [(232, 146), (276, 172)] + _jag((276, 172), (298, 276), 6, 12, r) + _jag((298, 276), (240, 262), 5, 11, r) + [(234, 226)]
    poly(cape, (0.046, 0.045, 0.047))
    # pale collar + red neck ribbon
    poly([(188, 144), (224, 144), (219, 170), (206, 180), (193, 170)], (0.84, 0.83, 0.81))
    poly([(201, 160), (211, 160), (214, 222), (206, 246), (198, 222)], (0.66, 0.135, 0.115))
    # back hair falling to the shoulders
    hair_back = [(174, 92), (168, 118)]
    hair_back += _jag((168, 118), (163, 168), 3, 5, r)
    hair_back += _jag((163, 168), (249, 166), 9, 11, r)
    hair_back += _jag((249, 166), (240, 116), 3, 5, r) + [(236, 86), (206, 58)]
    poly(hair_back, (0.60, 0.60, 0.60))
    layers.append((("ellipse", (186 * ss, 82 * ss, 228 * ss, 132 * ss)), (0.92, 0.88, 0.84)))
    # fringe sweeps across the brow; the face stays unmarked at this scale
    fringe = [(180, 112), (172, 88), (184, 62), (208, 50), (232, 60), (242, 88), (238, 110), (226, 100), (216, 112), (206, 96), (194, 110)]
    poly(fringe, (0.86, 0.86, 0.85))

    rgb = np.zeros((H0 * ss, W0 * ss, 3), "f4")
    alpha = np.zeros((H0 * ss, W0 * ss), "f4")
    for geom, color in layers:
        im = Image.new("L", (W0 * ss, H0 * ss), 0)
        d = ImageDraw.Draw(im)
        if isinstance(geom, tuple) and geom[0] == "ellipse":
            d.ellipse(geom[1], fill=255)
        else:
            d.polygon(geom, fill=255)
        m = np.asarray(im, "f4") / 255.0
        rgb = rgb * (1 - m[..., None]) + np.asarray(color, "f4") * m[..., None]
        alpha = np.maximum(alpha, m)
    # Soft fold shading over the dark cloth, then an ink-brush wobble on every edge.
    folds = fbm(H0 * ss, W0 * ss, 150, 3, seed + 2, cell_y=420)
    dark = (rgb.max(axis=2) < 0.25)[..., None]
    rgb = rgb + dark * np.clip(folds - 0.5, 0, 1)[..., None] * 0.12
    n = fbm(H0 * ss, W0 * ss, 42, 3, seed + 1)
    dx = (n - 0.5) * 10
    rgb = np.dstack([warp(rgb[..., i], dx, dx * 0.6) for i in range(3)])
    alpha = warp(alpha, dx, dx * 0.6)
    return np.dstack([rgb, alpha])


def resize_rgba(rgba, height):
    """Premultiplied Lanczos resize to a target height in pixels."""
    h, w = rgba.shape[:2]
    nw = max(1, round(w * height / h))
    pre = rgba.copy()
    pre[..., :3] *= pre[..., 3:]
    chans = [np.asarray(Image.fromarray(pre[..., i]).resize((nw, height), Image.LANCZOS), "f4") for i in range(4)]
    out = np.dstack(chans)
    a = np.clip(out[..., 3:], 1e-4, 1)
    out[..., :3] = np.clip(out[..., :3] / a, 0, 1)
    out[..., 3] = np.clip(out[..., 3], 0, 1)
    return out


def cast_figure_shadow(img, fig_rgba, x, y, cast=(0.86, 0.5), stretch=2.7, tone=0.34, seed=6, length_fade=True):
    """Skew the silhouette along the light direction and multiply it onto the snow."""
    h, w = img.shape[:2]
    fh, fw = fig_rgba.shape[:2]
    a = fig_rgba[..., 3]
    # map: foot line (bottom of figure) stays put, head is thrown along `cast`
    foot_y = fh * 0.92
    L = foot_y * stretch
    out_w = int(fw + L * cast[0] + 60)
    out_h = int(fh + L * cast[1] + 60)
    # affine from output (u,v) back to figure (s,t): t measured upward from the foot line.
    sil = Image.fromarray(a)
    coef = (1, -cast[0] / cast[1], 0,
            0, -1 / (stretch * cast[1]), foot_y)
    # keep output origin on the foot line
    res = sil.transform((out_w, out_h), Image.AFFINE, coef, resample=Image.BICUBIC)
    m = np.asarray(res, "f4")
    if length_fade:
        yy = np.linspace(0, 1, out_h)[:, None]
        m = m * np.clip(1.0 - 0.8 * yy / max(1e-3, (L * cast[1]) / out_h), 0.0, 1)
    m = ndi.gaussian_filter(m, 1.6)
    ax, ay = x, int(y + foot_y)
    canvas = np.zeros((h, w), "f4")
    x0, y0, x1, y1 = max(0, ax), max(0, ay), min(w, ax + out_w), min(h, ay + out_h)
    if x1 > x0 and y1 > y0:
        canvas[y0:y1, x0:x1] = m[y0 - ay:y1 - ay, x0 - ax:x1 - ax]
    return multiply(img, tone, np.clip(canvas, 0, 1) * 0.9)


# ---------------------------------------------------------------- ink corner -
def ink_mass(w, h, field, seed=5, cells=(30, 18, 10), reach=0.24):
    """Ink defined by a signed field (>0 solid), dissolving outward into square pixels."""
    r = np.random.default_rng(seed)
    d = field
    solid = sstep(-0.004, 0.022, d)
    alpha = solid.copy()
    tone = np.zeros((h, w), "f4")
    for k, cell in enumerate(cells):
        gw, gh = w // cell + 1, h // cell + 1
        rnd = r.random((gh, gw))
        shade = r.uniform(0.0, 0.26, (gh, gw))
        for gy in range(gh):
            y0 = gy * cell
            cy = min(h - 1, y0 + cell // 2)
            for gx in range(gw):
                x0 = gx * cell
                cx = min(w - 1, x0 + cell // 2)
                dv = d[cy, cx]
                if dv >= 0.012 or dv < -reach:
                    continue
                p = sstep(-reach, 0.012, dv) ** 2.5 * (0.5 + 0.13 * k)
                if rnd[gy, gx] < p:
                    alpha[y0:y0 + cell, x0:x0 + cell] = 1.0
                    tone[y0:y0 + cell, x0:x0 + cell] = shade[gy, gx]
    # Interior: wet ink pooled unevenly, with a few pale scratches.
    wet = fbm(h, w, 260, 5, seed + 2)
    scratch = streaks(h, w, -32, 360, 4, 3, seed + 3)
    lum = 0.06 + 0.075 * wet + 0.06 * np.clip(scratch - 0.72, 0, 1) + tone
    rgb = np.repeat(lum[..., None], 3, axis=2) * np.array([1.0, 0.985, 0.97], "f4")
    return np.dstack([rgb, alpha])


def ink_corner(w=1180, h=740, seed=5, margin=0.42):
    """Bottom-right ink mass. The field is below the dissolve reach on the crop's edges."""
    yy, xx = np.mgrid[0:h, 0:w].astype("f4")
    base = (xx / w + yy / h - 1.0 - margin) * 0.72
    n = fbm(h, w, 170, 5, seed + 1)
    brush = streaks(h, w, -34, 300, 16, 3, seed + 6)
    return ink_mass(w, h, base + (n - 0.5) * 0.17 + (brush - 0.5) * 0.08, seed, reach=0.2)


def ink_field(w, h, seed, fn, noise=0.17, reach=0.11):
    """Generic ink mass from fn(xx_norm, yy_norm) -> signed field."""
    yy, xx = np.mgrid[0:h, 0:w].astype("f4")
    base = fn(xx / w, yy / h)
    n = fbm(h, w, 190, 5, seed + 1)
    brush = streaks(h, w, -34, 340, 18, 3, seed + 6)
    return ink_mass(w, h, base + (n - 0.5) * noise + (brush - 0.5) * 0.05, seed, reach=reach)


# ---------------------------------------------------------------- fence -----
def fence(img, x, seed, ytop=-20, ybot=None, seglen=(120, 190), thick=13, shadow=(0.40, 0.46)):
    """Vertical run of rough sticks whose cross-rails throw grey bars to the right."""
    r = np.random.default_rng(seed)
    h, w = img.shape[:2]
    ybot = h + 20 if ybot is None else ybot
    stick, ds = canvas_mask(w, h)
    bar, db = canvas_mask(w, h)
    y = ytop
    while y < ybot:
        L = r.uniform(*seglen)
        gap = r.uniform(2, 14)
        n = 6
        px, py = x + r.normal(0, 3), y
        wp = thick * r.uniform(0.75, 1.15)
        for i in range(n):
            qx, qy = x + r.normal(0, 3.2), y + L * (i + 1) / n
            wq = thick * r.uniform(0.55, 1.15)
            thick_line(ds, (px, py), (qx, qy), wp, wq)
            if r.random() < 0.42:
                s = r.choice([-1, 1])
                thick_line(ds, (qx, qy), (qx + s * r.uniform(7, 19), qy - r.uniform(6, 27)), 6, 1.6)
            px, py, wp = qx, qy, wq
        by = y + L * r.uniform(0.15, 0.6)
        bl = r.uniform(130, 250)
        x1 = x + 3
        my = by + r.normal(0, 4)
        thick_line(db, (x1, by), (x1 + bl * 0.55, my), r.uniform(10, 17), r.uniform(7, 12), fill=int(r.uniform(190, 255)))
        thick_line(db, (x1 + bl * 0.55, my), (x1 + bl, my + r.normal(0, 7)), r.uniform(7, 11), r.uniform(1, 3), fill=int(r.uniform(120, 200)))
        if r.random() < 0.55:
            ex = x1 + r.uniform(30, 130)
            thick_line(db, (ex, my), (ex + r.uniform(25, 80), my + r.uniform(45, 105)), r.uniform(8, 13), r.uniform(1, 4), fill=int(r.uniform(120, 200)))
        y += L + gap
    b = warp(ndi.gaussian_filter(down(bar), 1.5), (fbm(h, w, 40, 3, seed + 1) - 0.5) * 8, (fbm(h, w, 40, 3, seed + 2) - 0.5) * 8)
    img = multiply(img, 1 - shadow[1], np.clip(b, 0, 1))
    s = roughen(down(stick), seed + 3, cell=7, amount=0.46, blur=0.8, soft=0.09)
    scuff = streaks(h, w, 90, 90, 3, 3, seed + 4)
    col = INK * (0.8 + 0.85 * np.clip(scuff - 0.45, 0, 1))[..., None]
    a = s[..., None]
    return img * (1 - a) + col * a


# ---------------------------------------------------------------- paintings -
def _vignette(h, w, seed, softness=0.2, reach=0.84):
    """Irregular worn-edge mask: the painting scrubs out into snow along dry strokes."""
    yy, xx = np.mgrid[0:h, 0:w].astype("f4")
    ex = (xx / w - 0.5) * 2
    ey = (yy / h - 0.5) * 2
    d = np.sqrt(ex ** 2 * 0.86 + ey ** 2 * 1.12)
    n = fbm(h, w, 80, 4, seed)
    s = streaks(h, w, 4, 110, 5, 3, seed + 1)
    v = reach - d + (n - 0.5) * 0.36 + (s - 0.5) * 0.26
    return sstep(0.0, softness, v)


def _onion(cx, top, base, rw):
    """Onion dome polygon from widest belly to a needle spire."""
    pts = []
    h = base - top
    for t in np.linspace(0, 1, 16):
        w = rw * math.sin(math.pi * min(1, t * 1.55 + 0.1)) ** 0.9 + 1.4 * (1 - t)
        pts.append((cx + w, base - h * t))
    return pts + [(2 * cx - x, y) for x, y in reversed(pts)]


def painting(kind, w=900, h=340, seed=1, vignette=True):
    """Small faded place-vignette behind a chapter label. Returns RGBA float."""
    r = np.random.default_rng(seed)
    pal = {
        "town":   dict(sky=(0.62, 0.55, 0.50), a=(0.29, 0.16, 0.11), b=(0.47, 0.27, 0.18), glow=(0.76, 0.58, 0.28)),
        "ember":  dict(sky=(0.26, 0.21, 0.19), a=(0.09, 0.08, 0.08), b=(0.18, 0.13, 0.11), glow=(0.68, 0.32, 0.13)),
        "dawn":   dict(sky=(0.56, 0.54, 0.54), a=(0.27, 0.26, 0.28), b=(0.39, 0.37, 0.38), glow=(0.78, 0.60, 0.53)),
        "chapel": dict(sky=(0.59, 0.51, 0.49), a=(0.32, 0.22, 0.21), b=(0.46, 0.34, 0.31), glow=(0.76, 0.60, 0.55)),
        "forest": dict(sky=(0.54, 0.54, 0.46), a=(0.25, 0.27, 0.21), b=(0.37, 0.38, 0.28), glow=(0.73, 0.71, 0.45)),
    }[kind]
    yy = np.linspace(0, 1, h)[:, None]
    n = fbm(h, w, 130, 4, seed + 3)
    rgb = np.zeros((h, w, 3), "f4")
    for i in range(3):
        rgb[..., i] = pal["sky"][i] * (0.84 + 0.3 * n) + (pal["glow"][i] - pal["sky"][i]) * np.exp(-((yy - 0.62) / 0.2) ** 2) * 0.72

    def paint(points, color):
        im = Image.new("L", (w, h), 0)
        ImageDraw.Draw(im).polygon(points, fill=255)
        m = np.asarray(im, "f4")[..., None] / 255.0
        return m, np.asarray(color, "f4")

    layers = []
    ground = int(h * 0.74)
    s = w / 900.0
    if kind in ("town", "chapel", "dawn", "ember"):
        for depth, col, hmin, hmax in ((0, pal["b"], 0.12, 0.3), (1, pal["a"], 0.09, 0.26)):
            x = -20
            while x < w:
                bw = r.uniform(30, 86) * s
                bh = h * r.uniform(hmin, hmax)
                top = ground - bh
                layers.append(([(x, ground + 8), (x, top), (x + bw, top), (x + bw, ground + 8)], col))
                if r.random() < 0.45:
                    layers.append(([(x - 3, top), (x + bw / 2, top - bw * 0.5), (x + bw + 3, top)], col))
                x += bw + r.uniform(-8, 6) * s
    if kind == "town":
        cx = w * 0.5
        gold = (0.70, 0.54, 0.27)
        layers.append(([(cx - 26 * s, ground), (cx - 21 * s, h * 0.34), (cx + 21 * s, h * 0.34), (cx + 26 * s, ground)], pal["a"]))
        layers.append((_onion(cx, h * 0.015, h * 0.36, 28 * s), gold))
        for ox in (-130, 142):
            ox = ox * s
            layers.append(([(cx + ox - 15 * s, ground), (cx + ox - 12 * s, h * 0.46), (cx + ox + 12 * s, h * 0.46), (cx + ox + 15 * s, ground)], pal["a"]))
            layers.append((_onion(cx + ox, h * 0.25, h * 0.47, 19 * s), (pal["b"][0] * 1.2, pal["b"][1] * 1.1, pal["b"][2])))
    elif kind == "chapel":
        for cx, tw, peak in ((w * 0.5, 40, 0.06), (w * 0.38, 26, 0.24), (w * 0.62, 26, 0.24)):
            layers.append(([(cx - tw * s, ground), (cx - tw * s, h * (peak + 0.24)), (cx, h * peak), (cx + tw * s, h * (peak + 0.24)), (cx + tw * s, ground)], pal["a"]))
    elif kind == "dawn":
        for cx, tw, peak in ((w * 0.33, 24, 0.27), (w * 0.67, 30, 0.2)):
            layers.append(([(cx - tw * s, ground), (cx - tw * 0.7 * s, h * (peak + 0.1)), (cx, h * peak), (cx + tw * 0.7 * s, h * (peak + 0.1)), (cx + tw * s, ground)], pal["a"]))
    elif kind == "ember":
        for cx in r.uniform(w * 0.15, w * 0.85, 8):
            layers.append(([(cx - 5 * s, ground), (cx - 2 * s, h * r.uniform(0.28, 0.55)), (cx + 4 * s, ground)], pal["a"]))
    elif kind == "forest":
        for _ in range(30):
            cx = r.uniform(30, w - 30)
            ww = r.uniform(3, 8) * s
            col = pal["a"] if r.random() < 0.5 else pal["b"]
            layers.append(([(cx - ww, ground + 10), (cx - ww * 0.3, h * r.uniform(0.04, 0.3)), (cx + ww * 0.3, h * r.uniform(0.04, 0.3)), (cx + ww, ground + 10)], col))
    for pts, col in layers:
        m, c = paint(pts, col)
        rgb = rgb * (1 - m) + c * m
    # ground snow with a dark band directly under the skyline so white labels hold up
    gm = sstep(0.70, 0.86, yy + (fbm(h, w, 44, 3, seed + 5)[:, :] - 0.5) * 0.09)[..., None]
    rgb = rgb * (1 - gm * 0.6) + np.array([0.40, 0.38, 0.37], "f4") * gm * 0.6
    # scumble, then scrub the edges into the snow
    dx = (fbm(h, w, 26, 3, seed + 7) - 0.5) * 8
    dy = (fbm(h, w, 26, 3, seed + 8) - 0.5) * 8
    rgb = np.dstack([warp(ndi.gaussian_filter(rgb[..., i], 0.7), dx, dy) for i in range(3)])
    rgb = rgb * (0.93 + 0.14 * streaks(h, w, 4, 150, 7, 3, seed + 9))[..., None]
    if vignette:
        band = np.exp(-((yy - 0.5) / 0.3) ** 2)[..., None]
        depth = {"ember": 0.15, "town": 0.42, "chapel": 0.5, "dawn": 0.55, "forest": 0.68}[kind]
        rgb = rgb * (1 - band * depth)
    a = _vignette(h, w, seed + 10) if vignette else np.ones((h, w), "f4")
    return np.dstack([np.clip(rgb, 0, 1), a])


# ---------------------------------------------------------------- burnt tag -
def burnt_paper(w=900, h=460, seed=2, emblem=True, stain=(0.47, 0.27, 0.20), burn_side="left"):
    """Aged form-paper note with a charred edge. Returns RGBA float."""
    r = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype("f4")
    edge = np.minimum.reduce([xx, w - 1 - xx, yy, h - 1 - yy]) / min(w, h)
    # the fire took more from one side and from the lower corner
    side = {"left": 1 - xx / w, "right": xx / w, "bottom": yy / h}[burn_side]
    burn = side ** 3 * 0.13 + ((1 - xx / w) * (yy / h)) ** 3 * 0.05
    n = fbm(h, w, 70, 5, seed + 1)
    d = edge - burn - 0.047 + (n - 0.5) * 0.085
    alpha = sstep(0.0, 0.006, d)

    base = np.array([0.845, 0.790, 0.680], "f4")
    mot = fbm(h, w, 190, 5, seed + 2)
    fibre = streaks(h, w, 3, 90, 2.5, 3, seed + 3)
    rgb = base[None, None] * (0.87 + 0.17 * mot + 0.05 * fibre)[..., None]
    # printed rules along the top, like a ledger form
    for y0 in (0.08, 0.12):
        band = np.exp(-((yy / h - y0) / 0.0035) ** 2) * 0.22
        rgb = rgb * (1 - band[..., None])
    for x0 in np.arange(0.05, 1.0, 0.045):
        tick = np.exp(-((xx / w - x0) / 0.0016) ** 2) * ((yy / h > 0.06) & (yy / h < 0.12)) * 0.2
        rgb = rgb * (1 - tick[..., None])
    # dried stain blooming from the right
    sm = sstep(0.42, 1.0, fbm(h, w, 170, 6, seed + 4) + (xx / w - 0.62) * 0.8) * 0.3
    rgb = rgb * (1 - sm[..., None]) + np.asarray(stain, "f4") * sm[..., None]
    # heat browning + char just inside the burnt edge
    scorch = np.exp(-np.clip(d, 0, None) / 0.05)
    rgb = rgb * (1 - scorch[..., None] * 0.68) + np.array([0.33, 0.20, 0.11], "f4") * scorch[..., None] * 0.68
    char = np.exp(-np.clip(d, 0, None) / 0.0105)
    rgb = rgb * (1 - char[..., None] * 0.97) + np.array([0.05, 0.04, 0.035], "f4") * char[..., None] * 0.97
    if emblem:
        im = Image.new("L", (w * 2, h * 2), 0)
        dr = ImageDraw.Draw(im)
        cx, cy, R = w, int(h * 0.58), int(h * 0.42)
        for k in range(8):
            ang = math.radians(k * 45 + 22.5)
            ln = R if k % 2 == 0 else R * 0.62
            tipx, tipy = cx + math.cos(ang) * ln, cy + math.sin(ang) * ln
            nx, ny = -math.sin(ang) * R * 0.07, math.cos(ang) * R * 0.07
            dr.polygon([(cx + nx, cy + ny), (tipx, tipy), (cx - nx, cy - ny)], fill=255)
        dr.ellipse([cx - R * 0.14, cy - R * 0.14, cx + R * 0.14, cy + R * 0.14], fill=0)
        em = np.asarray(im.resize((w, h), Image.LANCZOS), "f4") / 255.0
        wear = sstep(0.2, 0.62, fbm(h, w, 8, 3, seed + 6))
        a = (em * wear)[..., None] * 0.82
        rgb = rgb * (1 - a) + np.array([0.14, 0.12, 0.11], "f4") * a
    return np.dstack([np.clip(rgb, 0, 1), alpha])


# ---------------------------------------------------------------- pasting ---
def paste_rgba(img, rgba, x, y):
    """Composite a float RGBA array onto img with its top-left at (x, y)."""
    h, w = img.shape[:2]
    rh, rw = rgba.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + rw), min(h, y + rh)
    if x1 <= x0 or y1 <= y0:
        return img
    sub = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = sub[..., 3:]
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - a) + sub[..., :3] * a
    return img


def save_jpg(img, path, q=90):
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype("u1")).save(
        path, quality=q, subsampling=0, optimize=True)


def save_png(rgba, path):
    Image.fromarray((np.clip(rgba, 0, 1) * 255 + 0.5).astype("u1"), "RGBA").save(path, optimize=True)
