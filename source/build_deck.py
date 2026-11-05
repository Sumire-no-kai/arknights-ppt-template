#!/usr/bin/env python3
"""Assemble the template package (.pptx with samples, .potx clean) from ../assets.

Written directly as OOXML so that the theme fonts (Latin + East Asian), picture-filled
live text, custom-geometry placeholders and layout-level actions all stay under control.
"""
import io
import os
import random
import sys
import zipfile
from xml.sax.saxutils import escape

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ASSETS = os.path.join(ROOT, "assets")
SW, SH = 13.333, 7.5
EMU = 914400

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_IMG, REL_LAYOUT, REL_MASTER, REL_THEME = (f"{R_NS}/image", f"{R_NS}/slideLayout", f"{R_NS}/slideMaster", f"{R_NS}/theme")
REL_SLIDE, REL_CHART = f"{R_NS}/slide", f"{R_NS}/chart"


def E(v):
    return int(round(v * EMU))


def ang(deg):
    return int(deg * 60000)


class Part:
    """One XML part being authored: hands out shape ids and relationship ids."""

    def __init__(self):
        self.rels = []
        self._id = 1

    def sid(self):
        self._id += 1
        return self._id

    def rel(self, kind, target):
        for rid, k, t in self.rels:
            if k == kind and t == target:
                return rid
        rid = f"rId{len(self.rels) + 1}"
        self.rels.append((rid, kind, target))
        return rid

    def image(self, name):
        MEDIA.add(name)
        return self.rel(REL_IMG, f"../media/{name}")

    def rels_xml(self):
        body = "".join(f'<Relationship Id="{i}" Type="{k}" Target="{t}"/>' for i, k, t in self.rels)
        return XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>'


MEDIA = set()


# ------------------------------------------------------------------ colours ---
def color(c, alpha=None):
    a = f'<a:alpha val="{int(alpha * 1000)}"/>' if alpha is not None else ""
    if len(c) == 6 and all(ch in "0123456789ABCDEFabcdef" for ch in c):
        return f'<a:srgbClr val="{c}">{a}</a:srgbClr>'
    return f'<a:schemeClr val="{c}">{a}</a:schemeClr>'


def fill(c, alpha=None):
    return f"<a:solidFill>{color(c, alpha)}</a:solidFill>"


def line(c=None, w=1.0, alpha=None, cap=None):
    if c is None:
        return "<a:ln><a:noFill/></a:ln>"
    capx = f' cap="{cap}"' if cap else ""
    return f'<a:ln w="{int(w * 12700)}"{capx}>{fill(c, alpha)}</a:ln>'


def blip_text_fill(rid):
    return (f'<a:blipFill dpi="0" rotWithShape="1"><a:blip r:embed="{rid}"/><a:srcRect/>'
            f'<a:stretch><a:fillRect/></a:stretch></a:blipFill>')


TEXT_GLOW = ('<a:effectLst><a:outerShdw blurRad="76200" dist="0" algn="ctr" rotWithShape="0">'
             '<a:srgbClr val="120F0D"><a:alpha val="92000"/></a:srgbClr></a:outerShdw></a:effectLst>')


# ------------------------------------------------------------- text levels ---
def rpr_inner(c=None, font=None, fill_xml=None, glow=False):
    out = ""
    if fill_xml:
        out += fill_xml
    elif c:
        out += fill(c)
    if glow:
        out += TEXT_GLOW
    if font == "mj":
        out += '<a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/>'
    elif font == "mn":
        out += '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/>'
    return out


def lvl(n=1, sz=None, b=None, c=None, font=None, algn=None, marL=0, indent=0, spc=None, bullet=None,
        lnSpc=None, spcBef=None, spcAft=None, fill_xml=None, glow=False, i=None):
    attrs = f'marL="{E(marL)}" indent="{E(indent)}"'
    if algn:
        attrs += f' algn="{algn}"'
    inner = ""
    if lnSpc:
        inner += f'<a:lnSpc><a:spcPct val="{int(lnSpc * 1000)}"/></a:lnSpc>'
    inner += f'<a:spcBef><a:spcPts val="{int((spcBef or 0) * 100)}"/></a:spcBef>'
    inner += f'<a:spcAft><a:spcPts val="{int((spcAft or 0) * 100)}"/></a:spcAft>'
    if bullet:
        ch, bc = bullet
        inner += f'<a:buClr>{color(bc)}</a:buClr><a:buFont typeface="Times New Roman"/><a:buChar char="{ch}"/>'
    else:
        inner += "<a:buNone/>"
    r = ""
    if sz:
        r += f' sz="{int(sz * 100)}"'
    if b is not None:
        r += f' b="{1 if b else 0}"'
    if i is not None:
        r += f' i="{1 if i else 0}"'
    if spc is not None:
        r += f' spc="{int(spc)}"'
    return (f'<a:lvl{n}pPr {attrs}>{inner}<a:defRPr{r}>{rpr_inner(c, font, fill_xml, glow)}</a:defRPr></a:lvl{n}pPr>')


def lst(*levels):
    return f'<a:lstStyle>{"".join(levels)}</a:lstStyle>'


# --------------------------------------------------------------- paragraphs ---
def is_latin(t):
    return all(ord(ch) < 0x2E80 for ch in t)


def run(t, attrs="", inner=""):
    lang = "en-US" if is_latin(t) else "zh-CN"
    preserve = t != t.strip()
    return (f'<a:r><a:rPr lang="{lang}" altLang="{"zh-CN" if lang == "en-US" else "en-US"}"{attrs} dirty="0">{inner}</a:rPr>'
            f'<a:t>{escape(t)}</a:t></a:r>')


def para(t, level=0, attrs="", inner="", algn=None):
    if "\n" in t:
        runs = "<a:br/>".join(run(x, attrs, inner) for x in t.split("\n"))
        return f"<a:p>{runs}</a:p>"
    ppr = ""
    a = ""
    if level:
        a += f' lvl="{level}"'
    if algn:
        a += f' algn="{algn}"'
    if a:
        ppr = f"<a:pPr{a}/>"
    return f"<a:p>{ppr}{run(t, attrs, inner)}</a:p>"


def paras(items):
    """Accepts a string, or a list whose items are strings or (text, level) tuples."""
    if isinstance(items, str):
        items = [items]
    out = ""
    for it in items:
        if isinstance(it, tuple):
            out += para(it[0], it[1])
        else:
            out += para(it)
    return out


# ---------------------------------------------------------------- geometry ---
def xfrm(x, y, w, h, rot=0, tag="a:xfrm"):
    r = f' rot="{ang(rot)}"' if rot else ""
    return f'<{tag}{r}><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></{tag}>'


def custgeom(w, h, paths):
    """paths: [{'d':[('M',x,y),('L',x,y),('C',x1,y1,x2,y2,x,y),('Z',)], 'fill':bool, 'stroke':bool}] in unit coords.

    w, h are the shape's size in inches. Path units equal its EMU size, as PowerPoint writes them;
    some importers ignore the path scale and would otherwise draw the shape far too small.
    """
    W_, H_ = E(w), E(h)
    xml = ""
    for p in paths:
        a = f' w="{W_}" h="{H_}"'
        if not p.get("fill", True):
            a += ' fill="none"'
        if not p.get("stroke", True):
            a += ' stroke="0"'
        body = ""
        for c in p["d"]:
            pt = lambda i: f'<a:pt x="{int(c[i] * W_)}" y="{int(c[i + 1] * H_)}"/>'
            if c[0] == "M":
                body += f"<a:moveTo>{pt(1)}</a:moveTo>"
            elif c[0] == "L":
                body += f"<a:lnTo>{pt(1)}</a:lnTo>"
            elif c[0] == "C":
                body += f"<a:cubicBezTo>{pt(1)}{pt(3)}{pt(5)}</a:cubicBezTo>"
            else:
                body += "<a:close/>"
        xml += f"<a:path{a}>{body}</a:path>"
    return ('<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>'
            '<a:rect l="0" t="0" r="r" b="b"/>'
            f"<a:pathLst>{xml}</a:pathLst></a:custGeom>")


def rough_poly(pts, seed, jitter=0.012, steps=10):
    """Subdivide a closed polygon and jitter it, giving a torn, hand-cut outline."""
    r = random.Random(seed)
    out = []
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        for s in range(steps):
            t = s / steps
            jx = r.uniform(-jitter, jitter) if s else 0
            jy = r.uniform(-jitter, jitter) if s else 0
            out.append((min(1, max(0, x0 + (x1 - x0) * t + jx)), min(1, max(0, y0 + (y1 - y0) * t + jy))))
    d = [("M", *out[0])] + [("L", *p) for p in out[1:]] + [("Z",)]
    return [{"d": d}]


def shape(part, name, x, y, w, h, geom='<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>', fill_xml="<a:noFill/>",
          ln=None, text=None, body_attrs="", action=None, descr=None, rot=0, is_box=False, extra_sppr=""):
    i = part.sid()
    d = f' descr="{escape(descr)}"' if descr else ""
    link = ""
    if action:
        link = f'<a:hlinkClick r:id="" action="{action}"/>'
    cnv = f'<p:cNvPr id="{i}" name="{escape(name)}"{d}>{link}</p:cNvPr>' if link else f'<p:cNvPr id="{i}" name="{escape(name)}"{d}/>'
    tx = ""
    if text is not None:
        tx = f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0" {body_attrs}><a:noAutofit/></a:bodyPr><a:lstStyle/>{text}</p:txBody>'
    box = ' txBox="1"' if is_box else ""
    return (f'<p:sp><p:nvSpPr>{cnv}<p:cNvSpPr{box}/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr>{xfrm(x, y, w, h, rot)}{geom}{fill_xml}{ln or line()}{extra_sppr}</p:spPr>{tx}</p:sp>')


def picture(part, name, media, x, y, w, h, rot=0, descr=""):
    rid = part.image(media)
    i = part.sid()
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="{escape(name)}" descr="{escape(descr or name)}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr>{xfrm(x, y, w, h, rot)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')


def textbox(part, name, x, y, w, h, text, anchor="t"):
    return shape(part, name, x, y, w, h, text=text, body_attrs=f'anchor="{anchor}"', is_box=True)


# ------------------------------------------------------------------ chrome ---
MOUNTAIN = [{"d": [("M", .08, .82), ("L", .4, .28), ("L", .58, .58), ("L", .7, .42), ("L", .94, .82), ("Z",)]}]


def icon_frame(part, name, x, y, s, paths, stroke=False, c="tx2", frame_w=1.25):
    """Square frame plus glyph as two flat shapes: some importers drop custom geometry
    inside groups and ignore per-path fill flags, so neither is relied on here."""
    pad = s * 0.2
    q = s - 2 * pad
    style = dict(fill_xml="<a:noFill/>", ln=line(c, 1.25)) if stroke else dict(fill_xml=fill(c))
    return (shape(part, name + "框", x, y, s, s, ln=line(c, frame_w))
            + shape(part, name + "图标", x + pad, y + pad, q, q, geom=custgeom(q, q, paths), **style))


def page_number(part, c="bg1"):
    """Thick white frame sitting on the ink corner, holding a live slide-number field."""
    x, y, s = 12.46, 6.72, 0.54
    frame = shape(part, "页码框", x, y, s, s, ln=line(c, 2.75))
    fld = (f'<a:p><a:pPr algn="ctr"/><a:fld id="{{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}}" type="slidenum">'
           f'<a:rPr lang="en-US" sz="1400" b="0">{fill(c)}<a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/></a:rPr>'
           f"<a:t>‹#›</a:t></a:fld></a:p>")
    num = textbox(part, "页码", x, y, s, s, fld, anchor="ctr")
    return frame + num


def new_flag(part, x, y, w=0.82, h=0.3, seed=1, label="NEW"):
    """Swallowtail tag with a ragged edge; a native shape, so text and colour stay editable."""
    outline = [(0, 0), (.93, .06), (1, .02), (.9, .5), (1, .98), (.93, .94), (0, 1), (.11, .5)]
    geom = custgeom(w, h, rough_poly(outline, seed, jitter=0.008, steps=4))
    t = (f'<a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="en-US" sz="1200" b="1" spc="-20" dirty="0">{fill("F4F3F0")}'
         f'<a:latin typeface="+mj-lt"/></a:rPr><a:t>{label}</a:t></a:r></a:p>')
    return shape(part, "NEW 标记", x, y, w, h, geom=geom, fill_xml=fill("accent1"), text=t, body_attrs='anchor="ctr"', rot=-4)


def lock_icon(part, x, y, s=0.34, c="1A1918"):
    arc = [{"d": [("M", 0, 1), ("L", 0, .55), ("C", 0, -.15, 1, -.15, 1, .55), ("L", 1, 1)], "fill": False}]
    return (shape(part, "锁环", x + s * 0.24, y, s * 0.52, s * 0.5, geom=custgeom(s * 0.52, s * 0.5, arc), ln=line(c, 2.25))
            + shape(part, "锁身", x + s * 0.1, y + s * 0.44, s * 0.8, s * 0.56, fill_xml=fill(c)))


# ------------------------------------------------------------ placeholders ---
def ph(part, name, ptype, idx, x, y, w, h, style="", prompt=None, anchor=None, body="", geom=None, autofit=True, custom=True):
    """Placeholder on a layout/master: geometry, level styles and prompt text live here."""
    i = part.sid()
    t = f' type="{ptype}"' if ptype else ""
    sz = {"body": ' sz="quarter"', "pic": ' sz="half"', None: ' sz="half"', "dt": ' sz="half"', "ftr": ' sz="quarter"'}.get(ptype, "")
    ix = f' idx="{idx}"' if idx is not None else ""
    cp = ' hasCustomPrompt="1"' if prompt and custom else ""
    bp = f'{body}' + (f' anchor="{anchor}"' if anchor else "")
    fit = "<a:normAutofit/>" if autofit else "<a:noAutofit/>"
    lines = prompt if prompt is not None else ["单击此处编辑"]
    if isinstance(lines, str):
        lines = [lines]
    txt = "".join(para(l[0], l[1]) if isinstance(l, tuple) else para(l) for l in lines)
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{escape(name)}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            f'<p:nvPr><p:ph{t}{sz}{ix}{cp}/></p:nvPr></p:nvSpPr><p:spPr>{xfrm(x, y, w, h)}{geom or ""}</p:spPr>'
            f'<p:txBody><a:bodyPr {bp}>{fit}</a:bodyPr>{style or "<a:lstStyle/>"}{txt}</p:txBody></p:sp>')


def footers(part, c1="tx2", c2="accent3", x_right=12.34):
    """Top-right meta line, echoing the source's '作战结束时间' readout."""
    ft = lst(lvl(1, sz=12, c=c1, algn="r", font="mn", spc=20))
    dt = lst(lvl(1, sz=11, c=c2, algn="r", font="mn", spc=20))
    x = ph(part, "页眉文字", "ftr", 11, x_right - 4.6, 0.2, 4.6, 0.42, ft, prompt="项目名称 | 章节", anchor="ctr", autofit=False, custom=False,
           body='lIns="0" tIns="0" rIns="0" bIns="0"')
    x += ph(part, "日期", "dt", 10, 8.0, 0.64, 4.94, 0.26, dt, prompt="2026 / 11 / 04", anchor="ctr", autofit=False, custom=False,
            body='lIns="0" tIns="0" rIns="0" bIns="0"')
    return x


def title_block(part, w=9.6, x=0.62):
    """Fixed headline position: Songti headline plus a small Western subtitle under it."""
    t = ph(part, "标题", "title", None, x, 0.78, w, 0.72, None, prompt="在此输入页面标题", anchor="b", custom=True,
           body='lIns="0" tIns="0" rIns="0" bIns="0"')
    s = ph(part, "英文副标题", "body", 13, x, 1.5, w, 0.34, lst(lvl(1, sz=13, c="accent3", font="mj", spc=10)),
           prompt="Subtitle in a Western serif", anchor="t", body='lIns="0" tIns="30000" rIns="0" bIns="0"')
    return t + s


def bg_xml(part, media):
    rid = part.image(media)
    return (f'<p:bg><p:bgPr><a:blipFill dpi="0" rotWithShape="1"><a:blip r:embed="{rid}"/><a:srcRect/>'
            f"<a:stretch><a:fillRect/></a:stretch></a:blipFill><a:effectLst/></p:bgPr></p:bg>")


SPTREE_HEAD = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
               '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')


# ------------------------------------------------------------------ layouts ---
LAYOUTS = []


def layout(key, name, bg=None, ltype=None, master_shapes=True):
    def deco(fn):
        LAYOUTS.append(dict(key=key, name=name, bg=bg, ltype=ltype, master_shapes=master_shapes, fn=fn))
        return fn
    return deco


BODY_LEFT = 'lIns="0" tIns="0" rIns="0" bIns="0"'


def display_title_styles(part, big_sz=64, cn_sz=50, cn_tex="tx_ink.png", big_tex="tx_rust.png"):
    big = lst(lvl(1, sz=big_sz, b=True, font="mj", spc=-120, lnSpc=85, fill_xml=blip_text_fill(part.image(big_tex))))
    cn = lst(lvl(1, sz=cn_sz, b=True, font="mj", spc=60, lnSpc=90, fill_xml=blip_text_fill(part.image(cn_tex))))
    return big, cn


@layout("cover", "封面", bg="bg_cover.jpg", ltype="title", master_shapes=False)
def l_cover(p):
    big, cn = display_title_styles(p)
    x = ph(p, "西文大标题", "subTitle", 1, 0.5, 3.42, 8.2, 1.3, big, prompt="Display Title", anchor="b", body=BODY_LEFT)
    x += ph(p, "中文主标题", "ctrTitle", None, 0.56, 4.72, 8.0, 1.0, cn, prompt="在此输入演示标题", anchor="t", body=BODY_LEFT)
    x += ph(p, "说明", "body", 13, 0.58, 5.86, 6.8, 0.42, lst(lvl(1, sz=14, c="tx2", font="mn", spc=40)), prompt="汇报人 · 部门 · 日期", anchor="t", body=BODY_LEFT)
    x += footers(p, x_right=12.94)
    return x


def map_nodes(part, nodes):
    pw, ph_ = 3.3, 1.25
    pics, phs = "", ""
    style = lst(lvl(1, sz=20, b=True, c="F4F3F0", font="mj", algn="ctr", spc=30, glow=True),
                lvl(2, sz=10.5, c="F4F3F0", font="mn", algn="ctr", glow=True, spcBef=1))
    for n, (cx, cy, art) in enumerate(nodes):
        pics += picture(part, f"章节小画 {n + 1}", f"el_paint_{art}.png", cx - pw / 2, cy - ph_ / 2, pw, ph_, descr="装饰：褪色的地点小画")
        phs += ph(part, f"章节 {n + 1}", "body", 20 + n, cx - 1.45, cy - 0.42, 2.9, 0.84, style,
                  prompt=["章节名称", ("Chapter Name", 1)], anchor="ctr", body=BODY_LEFT)
    return pics + phs


def map_common(p, nodes):
    big, cn = display_title_styles(p, big_sz=52, cn_sz=42)
    x = picture(p, "焦痕纸签", "el_paper_tag.png", 0.2, 0.92, 3.3, 1.69, descr="装饰：边缘烧焦的纸签")
    x += map_nodes(p, nodes)
    x += ph(p, "纸签文字", "body", 19, 0.62, 1.72, 2.6, 0.72,
            lst(lvl(1, sz=15, b=True, c="tx1", font="mj", algn="ctr", spc=30),
                lvl(2, sz=9.5, c="tx1", font="mn", algn="ctr", spc=20)),
            prompt=["附加篇章", ("APPENDIX NOTE", 1)], anchor="ctr", body=BODY_LEFT)
    x += ph(p, "西文大标题", "body", 13, 0.5, 4.7, 4.1, 1.0, big, prompt="Contents", anchor="b", body=BODY_LEFT)
    x += ph(p, "目录标题", "title", None, 0.56, 5.7, 3.7, 0.86, cn, prompt="目录", anchor="t", body=BODY_LEFT)
    x += footers(p)
    return x


@layout("map5", "目录地图 · 5 章节", bg="bg_map5.jpg")
def l_map5(p):
    return map_common(p, [(6.1, 6.3, "town"), (9.05, 5.25, "chapel"), (11.15, 4.35, "forest"), (11.3, 2.72, "dawn"), (9.65, 1.5, "ember")])


@layout("map4", "目录地图 · 4 章节", bg="bg_map4.jpg")
def l_map4(p):
    return map_common(p, [(6.1, 6.3, "town"), (9.1, 5.1, "chapel"), (11.2, 3.7, "dawn"), (10.1, 1.75, "ember")])


@layout("map3", "目录地图 · 3 章节", bg="bg_map3.jpg")
def l_map3(p):
    return map_common(p, [(6.1, 6.3, "town"), (9.6, 4.5, "dawn"), (10.6, 2.2, "ember")])


@layout("section", "章节页", bg="bg_section.jpg", ltype="secHead", master_shapes=False)
def l_section(p):
    # Solid on purpose: a renderer without picture-filled text would draw black on the ink.
    num = lst(lvl(1, sz=104, b=False, c="F4F3F0", font="mj", spc=-300, lnSpc=80))
    tit = lst(lvl(1, sz=48, b=True, c="F4F3F0", font="mj", spc=60, lnSpc=90))
    x = ph(p, "章节序号", "body", 13, 5.75, 1.0, 5.0, 1.6, num, prompt="01", anchor="b", body=BODY_LEFT)
    x += ph(p, "章节标题", "title", None, 5.8, 2.68, 6.9, 1.0, tit, prompt="章节标题", anchor="t", body=BODY_LEFT)
    x += ph(p, "英文副标题", "body", 14, 5.82, 3.68, 6.9, 0.44, lst(lvl(1, sz=17, c="D9D8D5", font="mj", spc=20)), prompt="Chapter Title in Western Serif", anchor="t", body=BODY_LEFT)
    x += ph(p, "章节说明", "body", 15, 5.82, 4.32, 6.2, 1.3, lst(lvl(1, sz=14, c="BDBBB7", font="mn", lnSpc=125)), prompt="用一两句话说明这一章要解决的问题", anchor="t", body=BODY_LEFT)
    x += page_number(p)
    return x


@layout("content", "标题 + 正文", bg="bg_content.jpg", ltype="obj")
def l_content(p):
    x = title_block(p)
    x += ph(p, "正文", None, 1, 0.62, 2.05, 10.5, 4.45, None, prompt=["在此输入正文", ("第二级内容", 1), ("第三级内容", 2)], body=BODY_LEFT)
    x += footers(p)
    return x


@layout("twocol", "双栏 · 栅栏分隔", bg="bg_twocol.jpg", ltype="twoObj")
def l_twocol(p):
    head = lst(lvl(1, sz=20, b=True, c="tx1", font="mj", spc=20))
    x = title_block(p, w=5.6)
    x += ph(p, "左栏小标题", "body", 14, 0.62, 2.06, 5.5, 0.46, head, prompt="左栏小标题", anchor="b", body=BODY_LEFT)
    x += ph(p, "左栏内容", None, 15, 0.62, 2.62, 5.5, 3.9, None, prompt="左栏内容", body=BODY_LEFT)
    x += ph(p, "右栏小标题", "body", 16, 8.05, 2.06, 4.5, 0.46, head, prompt="右栏小标题", anchor="b", body=BODY_LEFT)
    x += ph(p, "右栏内容", None, 17, 8.05, 2.62, 4.5, 3.6, None, prompt="右栏内容", body=BODY_LEFT)
    x += footers(p)
    return x


TORN = custgeom(6.5, 5.7, rough_poly([(.012, .02), (.985, .008), (.992, .985), (.006, .992)], 21, jitter=0.0085, steps=26))


@layout("image", "图文 · 撕边图片", bg="bg_image.jpg", ltype="picTx")
def l_image(p):
    x = ph(p, "图片（单击图标插入）", "pic", 14, 0.55, 0.96, 6.5, 5.7, lst(lvl(1, sz=14, c="accent3", font="mn", algn="ctr")),
           prompt="单击图标插入图片：撕边轮廓由版式自动套用", geom=TORN, autofit=False)
    x += ph(p, "标题", "title", None, 7.5, 1.12, 5.2, 0.72, None, prompt="在此输入标题", anchor="b", body=BODY_LEFT)
    x += ph(p, "英文副标题", "body", 13, 7.5, 1.84, 5.2, 0.34, lst(lvl(1, sz=13, c="accent3", font="mj", spc=10)), prompt="Subtitle in a Western serif", body='lIns="0" tIns="30000" rIns="0" bIns="0"')
    x += ph(p, "正文", None, 1, 7.5, 2.42, 4.95, 3.9, None, prompt="在此输入说明文字", body=BODY_LEFT)
    x += footers(p)
    return x


@layout("cards", "三张焦痕便签", bg="bg_cards.jpg")
def l_cards(p):
    x = ""
    h_style = lst(lvl(1, sz=19, b=True, c="tx1", font="mj", spc=20, algn="l"))
    b_style = lst(lvl(1, sz=14, c="tx2", font="mn", lnSpc=118, bullet=None))
    cards = [(0.72, "el_note_a.png", -1.3, 0.74, 2.44), (4.82, "el_note_b.png", 0.8, 0.62, 2.5), (8.86, "el_note_c.png", -0.6, 0.56, 2.46)]
    for n, (cx, art, rot, _, _) in enumerate(cards):
        x += picture(p, f"便签 {n + 1}", art, cx, 2.0, 3.76, 4.25, rot=rot, descr="装饰：边缘烧焦的便签")
    x += title_block(p)
    for n, (cx, art, rot, inset, tw) in enumerate(cards):
        x += ph(p, f"便签 {n + 1} 标题", "body", 20 + n * 2, cx + inset, 2.72, tw, 0.5, h_style, prompt="便签标题", anchor="b", body=BODY_LEFT)
        x += ph(p, f"便签 {n + 1} 内容", "body", 21 + n * 2, cx + inset, 3.3, tw, 2.2, b_style, prompt="便签内容，保持简短", body=BODY_LEFT)
    x += footers(p)
    return x


@layout("timeline", "时间线 · 木桩与红绳", bg="bg_timeline.jpg")
def l_timeline(p):
    x = title_block(p)
    d_style = lst(lvl(1, sz=30, c="tx1", font="mj", spc=-60))
    h_style = lst(lvl(1, sz=16, b=True, c="tx1", font="mj", spc=20))
    b_style = lst(lvl(1, sz=14, c="tx2", font="mn", lnSpc=115))
    for i in range(5):
        cx = 0.62 + 2.38 * i
        x += ph(p, f"节点 {i + 1} 时间", "body", 20 + i * 3, cx, 2.3, 2.1, 0.62, d_style, prompt="2026.01", anchor="b", body=BODY_LEFT)
        x += ph(p, f"节点 {i + 1} 标题", "body", 21 + i * 3, cx, 4.72, 2.1, 0.4, h_style, prompt="阶段名称", anchor="t", body=BODY_LEFT)
        x += ph(p, f"节点 {i + 1} 说明", "body", 22 + i * 3, cx, 5.14, 2.1, 1.2, b_style, prompt="一句话说明", body=BODY_LEFT)
    x += footers(p)
    return x


@layout("data", "数据 · 大数字 + 图表", bg="bg_data.jpg")
def l_data(p):
    x = title_block(p)
    n_style = lst(lvl(1, sz=48, c="tx1", font="mj", spc=-100, lnSpc=85))
    c_style = lst(lvl(1, sz=13, c="accent3", font="mn"))
    for i in range(3):
        y = 2.08 + i * 1.47
        x += ph(p, f"数字 {i + 1}", "body", 20 + i * 2, 0.62, y, 3.3, 0.84, n_style, prompt="128%", anchor="b", body=BODY_LEFT)
        x += ph(p, f"数字 {i + 1} 说明", "body", 21 + i * 2, 0.62, y + 0.86, 3.3, 0.4, c_style, prompt="指标说明", body=BODY_LEFT)
    x += ph(p, "图表或表格", None, 1, 4.35, 2.05, 7.5, 4.3, lst(lvl(1, sz=14, c="accent3", font="mn")), prompt="单击图标插入图表或表格", autofit=False, body=BODY_LEFT)
    x += footers(p)
    return x


@layout("quote", "引言", bg="bg_quote.jpg")
def l_quote(p):
    mark = (f'<a:p><a:r><a:rPr lang="en-US" sz="11500" dirty="0"><a:blipFill dpi="0" rotWithShape="1"><a:blip r:embed="{p.image("tx_rust.png")}"/><a:srcRect/><a:stretch><a:fillRect/></a:stretch></a:blipFill>'
            f'<a:latin typeface="+mj-lt"/></a:rPr><a:t>“</a:t></a:r></a:p>')
    x = textbox(p, "引号", 0.72, 0.72, 2.0, 1.7, mark)
    x += ph(p, "引言", "title", None, 0.95, 2.1, 8.1, 2.7,
            lst(lvl(1, sz=34, b=True, c="tx1", font="mj", spc=40, lnSpc=118)), prompt="在此写下一句值得被记住的话", anchor="t", body=BODY_LEFT)
    x += ph(p, "出处", "body", 13, 0.98, 5.0, 8.0, 0.44, lst(lvl(1, sz=15, c="accent3", font="mj", spc=10)), prompt="—— 出处 / Source", body=BODY_LEFT)
    x += footers(p)
    return x


@layout("credits", "名单 · 团队与致谢", bg="bg_credits.jpg", master_shapes=False)
def l_credits(p):
    name = lst(lvl(1, sz=31, c="3F3D3A", font="mj", spc=-110, lnSpc=90),
               lvl(2, sz=13, c="8B8884", font="mn", spc=40, spcBef=2))
    x = ph(p, "名单标题", "title", None, 8.08, 1.32, 4.6, 0.62, lst(lvl(1, sz=24, b=True, c="3F3D3A", font="mj", spc=60)), prompt="致谢", anchor="b", body=BODY_LEFT)
    rows = [2.3, 3.32, 4.34]
    cols = [8.08, 10.4]
    n = 0
    for cx in cols:
        for y in rows:
            n += 1
            x += ph(p, f"姓名 {n}", "body", 19 + n, cx, y, 2.2, 0.92, name, prompt=["Name", ("姓名", 1)], anchor="t", body=BODY_LEFT)
    return x


@layout("end", "结束页", bg="bg_end.jpg", master_shapes=False)
def l_end(p):
    big, cn = display_title_styles(p, big_sz=64, cn_sz=50)
    x = ph(p, "西文大标题", "body", 13, 0.5, 2.3, 6.6, 1.2, big, prompt="Thank You", anchor="b", body=BODY_LEFT)
    x += ph(p, "中文主标题", "title", None, 0.56, 3.5, 6.6, 1.0, cn, prompt="感谢聆听", anchor="t", body=BODY_LEFT)
    x += ph(p, "联系方式", "body", 14, 0.58, 4.66, 6.4, 0.44, lst(lvl(1, sz=14, c="tx2", font="mn", spc=40)), prompt="姓名 · 邮箱 · 网站", body=BODY_LEFT)
    x += page_number(p)
    return x


@layout("blank", "空白", ltype="blank")
def l_blank(p):
    return footers(p)


# ------------------------------------------------------------------- master ---
def master_xml(part, layout_count):
    body_style = ""
    specs = [
        dict(n=1, sz=18, marL=0.24, indent=-0.24, bullet=("▪", "accent1"), spcBef=9),
        dict(n=2, sz=16, marL=0.52, indent=-0.22, bullet=("–", "accent3"), spcBef=5),
        dict(n=3, sz=14, marL=0.8, indent=-0.2, bullet=("·", "accent3"), spcBef=4),
        dict(n=4, sz=14, marL=1.06, indent=-0.2, bullet=("·", "accent3"), spcBef=4),
        dict(n=5, sz=14, marL=1.3, indent=-0.2, bullet=("·", "accent3"), spcBef=4),
    ]
    for s in specs:
        body_style += lvl(c="tx2", font="mn", lnSpc=118, algn="l", **s)
    title = lvl(1, sz=32, b=True, c="tx1", font="mj", algn="l", spc=40, lnSpc=95)
    sp = ph(part, "标题", "title", None, 0.62, 0.78, 9.6, 0.72, None, prompt="单击此处编辑母版标题样式", anchor="b", custom=False, body=BODY_LEFT)
    sp += ph(part, "正文", "body", 1, 0.62, 2.05, 10.5, 4.45, None, prompt=["单击此处编辑母版文本样式", ("第二级", 1), ("第三级", 2), ("第四级", 3), ("第五级", 4)], custom=False, body=BODY_LEFT)
    sp += footers(part)
    sp += icon_frame(part, "本章回想", 12.5, 0.2, 0.44, MOUNTAIN)
    sp += page_number(part)
    ids = "".join(f'<p:sldLayoutId id="{2147483649 + i}" r:id="rId{i + 1}"/>' for i in range(layout_count))
    other = "".join(f'<a:lvl{n}pPr marL="{E(0.5 * (n - 1))}" algn="l"><a:defRPr sz="1800">{fill("tx2")}<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/></a:defRPr></a:lvl{n}pPr>' for n in range(1, 6))
    return (XML + f'<p:sldMaster {NS}><p:cSld>{bg_xml(part, "bg_blank.jpg")}<p:spTree>{SPTREE_HEAD}{sp}</p:spTree></p:cSld>'
            '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            f'<p:sldLayoutIdLst>{ids}</p:sldLayoutIdLst>'
            f'<p:txStyles><p:titleStyle>{title}</p:titleStyle><p:bodyStyle>{body_style}</p:bodyStyle><p:otherStyle>{other}</p:otherStyle></p:txStyles></p:sldMaster>')


def layout_xml(part, L):
    bg = bg_xml(part, L["bg"]) if L["bg"] else ""
    body = L["fn"](part)
    t = f' type="{L["ltype"]}"' if L["ltype"] else ""
    sms = ' showMasterSp="0"' if not L["master_shapes"] else ""
    return (XML + f'<p:sldLayout {NS}{t} preserve="1" userDrawn="1"{sms}><p:cSld name="{escape(L["name"])}">{bg}'
            f'<p:spTree>{SPTREE_HEAD}{body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')


THEME = (XML + '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="雪原墨痕"><a:themeElements>'
         '<a:clrScheme name="雪原墨痕"><a:dk1><a:srgbClr val="1A1918"/></a:dk1><a:lt1><a:srgbClr val="F4F3F0"/></a:lt1>'
         '<a:dk2><a:srgbClr val="3B3936"/></a:dk2><a:lt2><a:srgbClr val="D9D8D5"/></a:lt2>'
         '<a:accent1><a:srgbClr val="A9251D"/></a:accent1><a:accent2><a:srgbClr val="C2622A"/></a:accent2>'
         '<a:accent3><a:srgbClr val="6E6B68"/></a:accent3><a:accent4><a:srgbClr val="5C3324"/></a:accent4>'
         '<a:accent5><a:srgbClr val="CDBFA3"/></a:accent5><a:accent6><a:srgbClr val="6B7A58"/></a:accent6>'
         '<a:hlink><a:srgbClr val="A9251D"/></a:hlink><a:folHlink><a:srgbClr val="6E6B68"/></a:folHlink></a:clrScheme>'
         '<a:fontScheme name="雪原墨痕"><a:majorFont><a:latin typeface="Didot"/><a:ea typeface="Songti SC"/><a:cs typeface=""/></a:majorFont>'
         '<a:minorFont><a:latin typeface="Times New Roman"/><a:ea typeface="Songti SC"/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
         '<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
         '<a:lnStyleLst><a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln><a:ln w="28575"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
         '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
         '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
         '</a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')


# ------------------------------------------------------------------- slides ---
class Slide:
    def __init__(self, key):
        self.key = key
        self.part = Part()
        self.shapes = ""

    def ph(self, name, ptype, idx, content):
        """Fill a placeholder. Geometry, fonts and colours all come from the layout."""
        p = self.part
        i = p.sid()
        t = f' type="{ptype}"' if ptype else ""
        ix = f' idx="{idx}"' if idx is not None else ""
        self.shapes += (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{escape(name)}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
                        f'<p:nvPr><p:ph{t}{ix}/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>{paras(content)}</p:txBody></p:sp>')
        return self

    def meta(self, section="雪线以北 | 冬季勘探汇报"):
        self.ph("页眉文字", "ftr", 11, section)
        self.ph("日期", "dt", 10, "2026 / 11 / 04")
        return self

    def add(self, xml):
        self.shapes += xml
        return self

    def pic_ph(self, name, idx, media, descr):
        p = self.part
        i = p.sid()
        rid = p.image(media)
        self.shapes += (f'<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="{escape(name)}" descr="{escape(descr)}"/>'
                        f'<p:cNvPicPr><a:picLocks noGrp="1" noChangeAspect="1"/></p:cNvPicPr><p:nvPr><p:ph type="pic" sz="half" idx="{idx}"/></p:nvPr></p:nvPicPr>'
                        f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>{xfrm(0.55, 0.96, 6.5, 5.7)}{TORN}</p:spPr></p:pic>')
        return self

    def xml(self):
        return (XML + f'<p:sld {NS}><p:cSld><p:spTree>{SPTREE_HEAD}{self.shapes}</p:spTree></p:cSld>'
                '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')


def table_xml(part, idx, x, y, w, rows, col_w):
    i = part.sid()
    grid = "".join(f'<a:gridCol w="{E(c)}"/>' for c in col_w)

    def border(tag, c=None, wd=0.75):
        if c is None:
            return f'<a:{tag} w="0"><a:noFill/></a:{tag}>'
        return f'<a:{tag} w="{int(wd * 12700)}" cap="flat" cmpd="sng" algn="ctr">{fill(c)}<a:prstDash val="solid"/></a:{tag}>'

    trs = ""
    for ri, row in enumerate(rows):
        tcs = ""
        for ci, t in enumerate(row):
            head = ri == 0
            sz, b, c = (15, 1, "tx1") if head else (14, 1 if ci == 0 else 0, "tx1" if ci == 0 else "tx2")
            if ci == len(row) - 1 and not head and t.startswith("▲"):
                c = "accent1"
            algn = "l" if ci == 0 else "r"
            lang = "en-US" if is_latin(t) else "zh-CN"
            body = (f'<a:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr algn="{algn}"/><a:r><a:rPr lang="{lang}" sz="{sz * 100}" b="{b}" dirty="0">{fill(c)}'
                    f'<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/></a:rPr><a:t>{escape(t)}</a:t></a:r></a:p></a:txBody>')
            bb = border("lnB", "tx1", 1.5) if head else border("lnB", "accent3", 0.5)
            tcs += (f'<a:tc>{body}<a:tcPr marL="45720" marR="91440" marT="64008" marB="64008" anchor="ctr">{border("lnL")}{border("lnR")}{border("lnT")}{bb}<a:noFill/></a:tcPr></a:tc>')
        trs += f'<a:tr h="{E(0.56)}">{tcs}</a:tr>'
    h = 0.56 * len(rows)
    return (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{i}" name="表格" descr="示例数据表格"/><p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>'
            f'<p:nvPr><p:ph idx="{idx}"/></p:nvPr></p:nvGraphicFramePr>{xfrm(x, y, w, h, tag="p:xfrm")}'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table"><a:tbl><a:tblPr firstRow="1"/><a:tblGrid>{grid}</a:tblGrid>{trs}</a:tbl></a:graphicData></a:graphic></p:graphicFrame>')


CHARTS = []


def chart_frame(part, idx, x, y, w, h, spec):
    CHARTS.append(spec)
    n = len(CHARTS)
    rid = part.rel(REL_CHART, f"../charts/chart{n}.xml")
    i = part.sid()
    return (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{i}" name="图表" descr="{escape(spec["descr"])}"/><p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>'
            f'<p:nvPr><p:ph idx="{idx}"/></p:nvPr></p:nvGraphicFramePr>{xfrm(x, y, w, h, tag="p:xfrm")}'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="{rid}"/></a:graphicData></a:graphic></p:graphicFrame>')


def chart_xml(spec):
    cats, series = spec["cats"], spec["series"]
    txt = lambda sz, c, b=0: (f'<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="{sz}" b="{b}">{fill(c)}<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/></a:defRPr></a:pPr><a:endParaRPr lang="zh-CN"/></a:p></c:txPr>')
    col = lambda i: "ABCDEFGHIJ"[i]
    ser = ""
    for i, (name, vals, c) in enumerate(series):
        ccat = "".join(f'<c:pt idx="{j}"><c:v>{escape(v)}</c:v></c:pt>' for j, v in enumerate(cats))
        cval = "".join(f'<c:pt idx="{j}"><c:v>{v}</c:v></c:pt>' for j, v in enumerate(vals))
        ser += (f'<c:ser><c:idx val="{i}"/><c:order val="{i}"/><c:tx><c:strRef><c:f>Sheet1!${col(i + 1)}$1</c:f><c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>{escape(name)}</c:v></c:pt></c:strCache></c:strRef></c:tx>'
                f'<c:spPr>{fill(c)}</c:spPr><c:invertIfNegative val="0"/>'
                f'<c:dLbls><c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>{txt(1200, "tx2")}<c:dLblPos val="outEnd"/><c:showLegendKey val="0"/><c:showVal val="1"/><c:showCatName val="0"/><c:showSerName val="0"/><c:showPercent val="0"/><c:showBubbleSize val="0"/></c:dLbls>'
                f'<c:cat><c:strRef><c:f>Sheet1!$A$2:$A${len(cats) + 1}</c:f><c:strCache><c:ptCount val="{len(cats)}"/>{ccat}</c:strCache></c:strRef></c:cat>'
                f'<c:val><c:numRef><c:f>Sheet1!${col(i + 1)}$2:${col(i + 1)}${len(cats) + 1}</c:f><c:numCache><c:formatCode>General</c:formatCode><c:ptCount val="{len(cats)}"/>{cval}</c:numCache></c:numRef></c:val></c:ser>')
    return (XML + '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<c:roundedCorners val="0"/><c:chart><c:autoTitleDeleted val="1"/><c:plotArea><c:layout/>'
            f'<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/>{ser}<c:gapWidth val="85"/><c:overlap val="-6"/><c:axId val="111111111"/><c:axId val="222222222"/></c:barChart>'
            f'<c:catAx><c:axId val="111111111"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="b"/><c:numFmt formatCode="General" sourceLinked="1"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:spPr>{line("tx1", 1.25)}</c:spPr>{txt(1300, "tx2")}<c:crossAx val="222222222"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/><c:noMultiLvlLbl val="0"/></c:catAx>'
            f'<c:valAx><c:axId val="222222222"/><c:scaling><c:orientation val="minMax"/><c:min val="0"/></c:scaling><c:delete val="1"/><c:axPos val="l"/><c:numFmt formatCode="General" sourceLinked="1"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:crossAx val="111111111"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>'
            f'<c:spPr><a:noFill/></c:spPr></c:plotArea><c:legend><c:legendPos val="t"/><c:overlay val="0"/>{txt(1200, "accent3")}</c:legend><c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart>'
            '<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr><c:externalData r:id="rId1"><c:autoUpdate val="0"/></c:externalData></c:chartSpace>')


def workbook_bytes(spec):
    """Minimal embedded workbook so 'Edit Data' works on the native chart."""
    cats, series = spec["cats"], spec["series"]
    col = lambda i: "ABCDEFGHIJ"[i]

    def sc(ref, s):
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(s)}</t></is></c>'

    rows = '<row r="1">' + sc("A1", " ") + "".join(sc(f"{col(i + 1)}1", s[0]) for i, s in enumerate(series)) + "</row>"
    for j, cat in enumerate(cats):
        rows += f'<row r="{j + 2}">' + sc(f"A{j + 2}", cat) + "".join(f'<c r="{col(i + 1)}{j + 2}"><v>{s[1][j]}</v></c>' for i, s in enumerate(series)) + "</row>"
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R_NS}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", XML + f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="{R_NS}"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R_NS}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", XML + f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>')
    return bio.getvalue()


SEARCH = [{"d": [("M", .1, .42), ("C", .1, .0, .74, .0, .74, .42), ("C", .74, .84, .1, .84, .1, .42), ("Z",), ("M", .66, .66), ("L", .95, .95)], "fill": False}]
PLAY = [{"d": [("M", .2, .08), ("L", .92, .5), ("L", .2, .92), ("Z",)]}]
REFRESH = [{"d": [("M", .85, .32), ("C", .68, .02, .22, .02, .1, .42), ("M", .15, .68), ("C", .32, .98, .78, .98, .9, .58),
                  ("M", .88, .06), ("L", .85, .32), ("L", .6, .28), ("M", .12, .94), ("L", .15, .68), ("L", .4, .72)], "fill": False}]


def sample_slides():
    out = []

    s = Slide("cover")
    s.ph("西文大标题", "subTitle", 1, "North of the Snowline")
    s.ph("中文主标题", "ctrTitle", None, "雪线以北")
    s.ph("说明", "body", 13, "冬季勘探汇报 · 示例内容，可直接替换")
    s.meta()
    out.append(s)

    s = Slide("map5")
    s.ph("纸签文字", "body", 19, ["附录：观测手记", ("FIELD NOTES", 1)])
    s.ph("西文大标题", "body", 13, "Contents")
    s.ph("目录标题", "title", None, "目录")
    for i, (cn, en) in enumerate([("出发之前", "Before We Set Out"), ("穿过林线", "Through the Treeline"),
                                  ("风雪　　之中", "11月8日 16:00 后开启"), ("晨光所见", "What the Dawn Showed"),
                                  ("余烬之下", "Beneath the Embers")]):
        s.ph(f"章节 {i + 1}", "body", 20 + i, [cn, (en, 1)])
    s.meta("雪线以北 | 目录")
    s.add(new_flag(s.part, 2.86, 0.86, seed=2))
    s.add(new_flag(s.part, 12.05, 2.3, seed=3))
    s.add(lock_icon(s.part, 10.97, 4.05, 0.36, c="F4F3F0"))
    out.append(s)

    s = Slide("section")
    s.ph("章节序号", "body", 13, "01")
    s.ph("章节标题", "title", None, "穿过林线")
    s.ph("英文副标题", "body", 14, "Through the Treeline")
    s.ph("章节说明", "body", 15, "这一章回顾我们从哪里出发、走过了哪些路，以及在林线附近做出的三个关键判断。")
    out.append(s)

    s = Slide("content")
    s.ph("标题", "title", None, "三个判断决定了路线")
    s.ph("英文副标题", "body", 13, "Three calls that set the route")
    s.ph("正文", None, 1, [
        "先走高线：多绕两天，换来全程更稳的补给窗口",
        ("补给点从四个减到两个，单点负载需要提前预留", 1),
        ("高线气温更低，装备清单同步调整", 1),
        "分队前进：先遣组负责探路，主力保持一日路程",
        "每日回传：无论进展如何，傍晚固定同步一次位置与判断依据",
    ])
    s.meta("雪线以北 | 穿过林线")
    out.append(s)

    s = Slide("twocol")
    s.ph("标题", "title", None, "栅栏两侧的取舍")
    s.ph("英文副标题", "body", 13, "What we kept, what we left")
    s.ph("左栏小标题", "body", 14, "留下来的")
    s.ph("左栏内容", None, 15, ["轻量化补给方案，已验证可行", "每日固定时点的回传机制", "先遣组与主力的一日间距"])
    s.ph("右栏小标题", "body", 16, "放下的")
    s.ph("右栏内容", None, 17, ["低线捷径：节省时间但风险难控", "第三补给点：投入大于收益", "夜间行进：能见度不足"])
    s.meta("雪线以北 | 穿过林线")
    out.append(s)

    s = Slide("image")
    s.pic_ph("示例图片", 14, "sample_photo.jpg", "示例图片：雪线边缘的小镇剪影，可替换")
    s.ph("标题", "title", None, "雪线上的最后一座镇子")
    s.ph("英文副标题", "body", 13, "The last town before the snow")
    s.ph("正文", None, 1, ["这里是全程最后一个稳定补给点", "向北一百二十公里内没有固定建筑", "所有无法返程的物资都在此处封存"])
    s.meta("雪线以北 | 出发之前")
    out.append(s)

    s = Slide("cards")
    s.ph("标题", "title", None, "风雪里记下的三件事")
    s.ph("英文副标题", "body", 13, "Three notes from the storm")
    notes = [("路线", "预设路线只是起点，每天都要依据实际雪况重新确认。"),
             ("补给", "轻装的前提是节点可靠。任何一个节点失效，都要有替代方案。"),
             ("队伍", "最有用的信息往往来自先遣组，让它尽早传回主力。")]
    for i, (h, b) in enumerate(notes):
        s.ph(f"便签 {i + 1} 标题", "body", 20 + i * 2, h)
        s.ph(f"便签 {i + 1} 内容", "body", 21 + i * 2, b)
    s.meta("雪线以北 | 风雪之中")
    out.append(s)

    s = Slide("timeline")
    s.ph("标题", "title", None, "每一根木桩都是一次确认")
    s.ph("英文副标题", "body", 13, "Every post marks a checkpoint")
    tl = [("11.02", "出发", "完成物资封存与最后校验"), ("11.09", "越过林线", "切换高线路线，先遣组前出"),
          ("11.16", "遭遇风雪", "原地等待三日，修订补给计划"), ("11.24", "抵达营地", "建立北部观测点"), ("12.01", "返程", "沿原路回撤，回收标记")]
    for i, (d, h, b) in enumerate(tl):
        s.ph(f"节点 {i + 1} 时间", "body", 20 + i * 3, d)
        s.ph(f"节点 {i + 1} 标题", "body", 21 + i * 3, h)
        s.ph(f"节点 {i + 1} 说明", "body", 22 + i * 3, b)
    s.meta("雪线以北 | 风雪之中")
    out.append(s)

    s = Slide("data")
    s.ph("标题", "title", None, "高线路线让补给更稳")
    s.ph("英文副标题", "body", 13, "Sample data, replace with your own")
    for i, (n, c) in enumerate([("92%", "补给准时率（示例）"), ("3.4 天", "平均节点间隔（示例）"), ("17", "有效观测日（示例）")]):
        s.ph(f"数字 {i + 1}", "body", 20 + i * 2, n)
        s.ph(f"数字 {i + 1} 说明", "body", 21 + i * 2, c)
    s.add(chart_frame(s.part, 1, 4.35, 2.05, 7.5, 4.3, dict(
        descr="示例柱状图：高线路线与低线路线四周补给量对比",
        cats=["第一周", "第二周", "第三周", "第四周"],
        series=[("低线路线", [38, 42, 31, 35], "accent3"), ("高线路线", [44, 52, 58, 63], "accent1")])))
    s.meta("雪线以北 | 晨光所见")
    out.append(s)

    s = Slide("content")
    s.ph("标题", "title", None, "两条路线的逐项对比")
    s.ph("英文副标题", "body", 13, "Sample table, replace with your own")
    s.add(table_xml(s.part, 1, 0.62, 2.1, 10.6, [
        ["指标", "低线路线", "高线路线", "差异"],
        ["全程里程（公里）", "412", "468", "+56"],
        ["补给准时率", "71%", "92%", "▲ 21%"],
        ["平均节点间隔（天）", "4.8", "3.4", "▲ 1.4"],
        ["有效观测日", "11", "17", "▲ 6"],
    ], [4.2, 2.1, 2.1, 2.2]))
    s.meta("雪线以北 | 晨光所见")
    out.append(s)

    s = Slide("quote")
    s.ph("引言", "title", None, "雪会盖住足迹，\n但走过的路不会因此消失。")
    s.ph("出处", "body", 13, "—— 勘探队手记 / Field Notes")
    s.meta("雪线以北 | 余烬之下")
    out.append(s)

    s = Slide("credits")
    s.ph("名单标题", "title", None, "勘探队")
    for i, (en, cn) in enumerate([("Aurel", "奥瑞尔"), ("Vesna", "维斯娜"), ("Tomas", "托马斯"), ("Mirela", "米蕾拉"), ("Ilan", "伊兰")]):
        s.ph(f"姓名 {i + 1}", "body", 20 + i, [en, (cn, 1)])
    out.append(s)

    s = Slide("end")
    s.ph("西文大标题", "body", 13, "Thank You")
    s.ph("中文主标题", "title", None, "感谢聆听")
    s.ph("联系方式", "body", 14, "在此填写姓名 · 邮箱 · 网站")
    out.append(s)

    # ---- element sheet: everything here is meant to be copied elsewhere --------
    s = Slide("blank")
    p = s.part
    head = lambda t: f'<a:p><a:r><a:rPr lang="zh-CN" sz="1300" b="1" dirty="0">{fill("tx1")}</a:rPr><a:t>{escape(t)}</a:t></a:r></a:p>'
    note = lambda t, c="accent3", sz=1100: f'<a:p><a:r><a:rPr lang="zh-CN" sz="{sz}" dirty="0">{fill(c)}</a:rPr><a:t>{escape(t)}</a:t></a:r></a:p>'
    s.add(textbox(p, "标题", 0.62, 0.78, 8, 0.66, f'<a:p><a:r><a:rPr lang="zh-CN" sz="3200" b="1" spc="40" dirty="0">{fill("tx1")}<a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/></a:rPr><a:t>组件库</a:t></a:r></a:p>', anchor="b"))
    s.add(textbox(p, "说明", 0.62, 1.46, 9.2, 0.3, f'<a:p><a:r><a:rPr lang="zh-CN" sz="1300" dirty="0">{fill("accent3")}</a:rPr><a:t>这一页不用于汇报：需要时复制元素到其他页，用完可删除</a:t></a:r></a:p>'))
    # palette
    s.add(textbox(p, "配色标题", 0.62, 2.0, 3, 0.28, head("主题配色")))
    swatches = [("tx1", "墨黑"), ("tx2", "炭灰"), ("accent3", "影灰"), ("bg2", "灰雪"), ("accent1", "血红"), ("accent2", "锈橙"), ("accent4", "焦褐"), ("accent5", "旧纸"), ("accent6", "枯绿")]
    for i, (c, n) in enumerate(swatches):
        x0 = 0.62 + (i % 5) * 0.72
        y0 = 2.34 + (i // 5) * 0.86
        s.add(shape(p, f"色块 {n}", x0, y0, 0.6, 0.48, fill_xml=fill(c), ln=line("accent3", 0.5)))
        s.add(textbox(p, f"色名 {n}", x0, y0 + 0.5, 0.66, 0.26, note(n)))
    # type
    s.add(textbox(p, "字体标题", 4.6, 2.0, 3.6, 0.28, head("字体（主题字体，可一键替换）")))
    s.add(textbox(p, "字体示例", 4.6, 2.32, 3.6, 0.6, f'<a:p><a:r><a:rPr lang="en-US" sz="3200" spc="-100" dirty="0">{fill("tx1")}<a:latin typeface="+mj-lt"/></a:rPr><a:t>Didot</a:t></a:r><a:r><a:rPr lang="zh-CN" sz="2600" b="1" dirty="0">{fill("tx1")}<a:ea typeface="+mj-ea"/></a:rPr><a:t>  宋体标题</a:t></a:r></a:p>'))
    s.add(textbox(p, "正文示例", 4.6, 2.96, 3.6, 0.8, f'<a:p><a:r><a:rPr lang="zh-CN" sz="1400" dirty="0">{fill("tx2")}</a:rPr><a:t>正文使用宋体，西文 Times New Roman。</a:t></a:r></a:p>' + note("Windows 上可把主题字体换成 Bodoni MT + 思源宋体")))
    # controls
    s.add(textbox(p, "控件标题", 8.5, 2.0, 3.6, 0.28, head("原生控件（可改字、改色）")))
    s.add(new_flag(p, 8.5, 2.36, seed=5))
    s.add(lock_icon(p, 9.56, 2.33, 0.36))
    s.add(textbox(p, "解锁时间", 10.04, 2.38, 2.5, 0.3, note("11月8日 16:00 后开启", "tx2", 1200)))
    s.add(icon_frame(p, "搜索", 8.5, 2.92, 0.46, SEARCH, stroke=True))
    s.add(icon_frame(p, "播放", 9.08, 2.92, 0.46, PLAY))
    s.add(icon_frame(p, "回想", 9.66, 2.92, 0.46, MOUNTAIN))
    s.add(icon_frame(p, "刷新", 10.24, 2.92, 0.46, REFRESH, stroke=True))
    # art
    s.add(textbox(p, "素材标题", 0.62, 4.02, 6, 0.28, head("透明底素材（assets 文件夹内有高清原图）")))
    s.add(picture(p, "人物", "el_figure.png", 0.5, 4.3, 1.6, 2.4, descr="素材：披斗篷的小人"))
    s.add(picture(p, "足迹", "el_footprints.png", 2.1, 4.34, 0.55, 2.38, descr="素材：足迹"))
    s.add(picture(p, "红绳", "el_ribbon_red.png", 2.8, 4.34, 3.2, 0.55, descr="素材：红色布带"))
    s.add(picture(p, "橙绳", "el_ribbon_rust.png", 2.8, 4.85, 3.2, 0.55, descr="素材：橙色布带"))
    s.add(picture(p, "小画 1", "el_paint_town.png", 2.75, 5.4, 3.2, 1.21, descr="素材：褪色小镇"))
    s.add(picture(p, "小画 2", "el_paint_ember.png", 5.95, 5.4, 3.2, 1.21, descr="素材：余烬地平线"))
    s.add(picture(p, "焦痕纸签", "el_paper_tag.png", 6.2, 4.02, 2.7, 1.38, descr="素材：焦痕纸签"))
    s.add(picture(p, "便签", "el_note_c.png", 9.0, 3.72, 2.1, 2.38, descr="素材：焦痕便签"))
    s.meta("组件库 | 不用于汇报")
    out.append(s)
    return out


# ------------------------------------------------------------------ package ---
def build(path, template=False, thumbnail=None):
    MEDIA.clear()
    CHARTS.clear()
    files = {}

    keys = [L["key"] for L in LAYOUTS]
    # Layouts first so that the master's rel ids rId1..N line up with its layout id list.
    master = Part()
    for i in range(len(LAYOUTS)):
        master.rel(REL_LAYOUT, f"../slideLayouts/slideLayout{i + 1}.xml")
    master.rel(REL_THEME, "../theme/theme1.xml")
    files["ppt/slideMasters/slideMaster1.xml"] = master_xml(master, len(LAYOUTS))
    files["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = master.rels_xml()
    for i, L in enumerate(LAYOUTS):
        p = Part()
        p.rel(REL_MASTER, "../slideMasters/slideMaster1.xml")
        files[f"ppt/slideLayouts/slideLayout{i + 1}.xml"] = layout_xml(p, L)
        files[f"ppt/slideLayouts/_rels/slideLayout{i + 1}.xml.rels"] = p.rels_xml()
    files["ppt/theme/theme1.xml"] = THEME

    if template:
        slides = [Slide("cover")]
        s = slides[0]
        for n, t, ix in (("西文大标题", "subTitle", 1), ("中文主标题", "ctrTitle", None), ("说明", "body", 13)):
            pid = s.part.sid()
            tt = f' type="{t}"'
            ii = f' idx="{ix}"' if ix is not None else ""
            s.shapes += (f'<p:sp><p:nvSpPr><p:cNvPr id="{pid}" name="{n}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph{tt}{ii}/></p:nvPr></p:nvSpPr><p:spPr/>'
                         '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="zh-CN"/></a:p></p:txBody></p:sp>')
    else:
        slides = sample_slides()
    for i, s in enumerate(slides):
        s.part.rels.insert(0, ("rIdLayout", REL_LAYOUT, f"../slideLayouts/slideLayout{keys.index(s.key) + 1}.xml"))
        files[f"ppt/slides/slide{i + 1}.xml"] = s.xml()
        files[f"ppt/slides/_rels/slide{i + 1}.xml.rels"] = s.part.rels_xml()

    for n, spec in enumerate(CHARTS, 1):
        files[f"ppt/charts/chart{n}.xml"] = chart_xml(spec)
        files[f"ppt/charts/_rels/chart{n}.xml.rels"] = XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R_NS}/package" Target="../embeddings/Microsoft_Excel_Sheet{n}.xlsx"/></Relationships>'
        files[f"ppt/embeddings/Microsoft_Excel_Sheet{n}.xlsx"] = workbook_bytes(spec)

    pres_rels = Part()
    pres_rels.rel(REL_MASTER, "slideMasters/slideMaster1.xml")
    sld_ids = ""
    for i in range(len(slides)):
        rid = pres_rels.rel(REL_SLIDE, f"slides/slide{i + 1}.xml")
        sld_ids += f'<p:sldId id="{256 + i}" r:id="{rid}"/>'
    pres_rels.rel(f"{R_NS}/presProps", "presProps.xml")
    pres_rels.rel(f"{R_NS}/viewProps", "viewProps.xml")
    pres_rels.rel(f"{R_NS}/theme", "theme/theme1.xml")
    pres_rels.rel(f"{R_NS}/tableStyles", "tableStyles.xml")
    default_text = "".join(f'<a:lvl{n}pPr marL="{E(0.5 * (n - 1))}" algn="l"><a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/></a:defRPr></a:lvl{n}pPr>' for n in range(1, 6))
    files["ppt/presentation.xml"] = (XML + f'<p:presentation {NS} saveSubsetFonts="1" autoCompressPictures="0"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                                     f'<p:sldIdLst>{sld_ids}</p:sldIdLst><p:sldSz cx="{E(SW)}" cy="{E(SH)}"/><p:notesSz cx="6858000" cy="9144000"/>'
                                     f'<p:defaultTextStyle><a:defPPr><a:defRPr lang="zh-CN"/></a:defPPr>{default_text}</p:defaultTextStyle></p:presentation>')
    files["ppt/_rels/presentation.xml.rels"] = pres_rels.rels_xml()
    files["ppt/presProps.xml"] = XML + f'<p:presentationPr {NS}/>'
    files["ppt/viewProps.xml"] = XML + f'<p:viewPr {NS}/>'
    files["ppt/tableStyles.xml"] = XML + '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>'

    main_ct = ("application/vnd.openxmlformats-officedocument.presentationml.template.main+xml" if template
               else "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml")
    over = [("/ppt/presentation.xml", main_ct),
            ("/ppt/slideMasters/slideMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"),
            ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
            ("/ppt/presProps.xml", "application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"),
            ("/ppt/viewProps.xml", "application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"),
            ("/ppt/tableStyles.xml", "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"),
            ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
            ("/docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml")]
    for i in range(len(LAYOUTS)):
        over.append((f"/ppt/slideLayouts/slideLayout{i + 1}.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"))
    for i in range(len(slides)):
        over.append((f"/ppt/slides/slide{i + 1}.xml", "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"))
    for n in range(1, len(CHARTS) + 1):
        over.append((f"/ppt/charts/chart{n}.xml", "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"))
    defaults = ('<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="jpeg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/>'
                '<Default Extension="xlsx" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"/>')
    files["[Content_Types].xml"] = XML + f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">{defaults}' + "".join(f'<Override PartName="{a}" ContentType="{b}"/>' for a, b in over) + "</Types>"
    root_rels = (f'<Relationship Id="rId1" Type="{R_NS}/officeDocument" Target="ppt/presentation.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                 f'<Relationship Id="rId3" Type="{R_NS}/extended-properties" Target="docProps/app.xml"/>')
    if thumbnail and os.path.exists(thumbnail):
        root_rels += '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail" Target="docProps/thumbnail.jpeg"/>'
        files["docProps/thumbnail.jpeg"] = open(thumbnail, "rb").read()
    files["_rels/.rels"] = XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{root_rels}</Relationships>'
    files["docProps/core.xml"] = (XML + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                                  '<dc:title>雪原墨痕 PPT 模板</dc:title><dcterms:created xsi:type="dcterms:W3CDTF">2026-11-04T00:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2026-11-04T00:00:00Z</dcterms:modified></cp:coreProperties>')
    files["docProps/app.xml"] = XML + f'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Slides>{len(slides)}</Slides></Properties>'

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", files.pop("[Content_Types].xml"))
        for name, data in files.items():
            z.writestr(name, data)
        for m in sorted(MEDIA):
            z.write(os.path.join(ASSETS, m), f"ppt/media/{m}", compress_type=zipfile.ZIP_STORED)
    print(os.path.basename(path), f"{os.path.getsize(path) / 1e6:.1f} MB", len(slides), "slides", len(LAYOUTS), "layouts")


if __name__ == "__main__":
    thumb = os.path.join(ROOT, "source", "thumbnail.jpeg")
    build(os.path.join(ROOT, "雪原墨痕-示例.pptx"), False, thumb)
    build(os.path.join(ROOT, "雪原墨痕-模板.potx"), True, thumb)
