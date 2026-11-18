"""Generates SYNTHETIC test images (no real people, no real documents, no real places' private data).

Runs inside an image that has Pillow + numpy (the ML image), with --network none:
  docker run --rm --network none --entrypoint python -v OUT:/out -v tools:/tools:ro ML_IMAGE -I /tools/gen_synthetic.py /out [seed]

Everything is drawn procedurally: face-like portraits (several fictional "identities" with small pose/light variations),
text pages (generic invented text) and abstract scenes. EXIF is written with Pillow (camera make/model, local date, GPS of
public city centres). Writes /out/manifest.json (kind, identity, expected EXIF) and the JPEG/PNG files.
"""
import json, math, random, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.TiffImagePlugin import IFDRational

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 20261114
SS = 2  # supersampling


def font(size):
    return ImageFont.load_default(size)


def grad(w, h, top, bottom):
    a = np.linspace(0, 1, h)[:, None, None]
    t, b = np.array(top, float), np.array(bottom, float)
    return Image.fromarray((t * (1 - a) + b * a).repeat(w, axis=1).astype('uint8'), 'RGB')


def shade_ellipse(size, box, base, light=(-0.35, -0.45), strength=0.35):
    """Ellipse filled with a radial-shaded colour (gives a 3-D look)."""
    w, h = size
    x0, y0, x1, y1 = box
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    yy, xx = np.mgrid[0:h, 0:w]
    nx, ny = (xx - cx) / rx, (yy - cy) / ry
    d = np.sqrt(nx ** 2 + ny ** 2)
    k = 1 - strength * np.clip(((nx - light[0]) ** 2 + (ny - light[1]) ** 2) ** 0.5 / 1.6, 0, 1)
    img = np.zeros((h, w, 3), float)
    for c in range(3): img[..., c] = base[c] * k
    mask = (d <= 1).astype('uint8') * 255
    return Image.fromarray(np.clip(img, 0, 255).astype('uint8'), 'RGB'), Image.fromarray(mask, 'L').filter(ImageFilter.GaussianBlur(1.5 * SS))


def face(identity, variant, W=900, H=1100):
    r = random.Random(identity['seed'] * 100 + variant)
    w, h = W * SS, H * SS
    bg = grad(w, h, identity['bg_top'], identity['bg_bottom'])
    bg = bg.filter(ImageFilter.GaussianBlur(10 * SS))
    d = ImageDraw.Draw(bg)
    cx = w / 2 + r.uniform(-20, 20) * SS
    cy = h * 0.46 + r.uniform(-15, 15) * SS
    fw, fh = identity['face_w'] * SS, identity['face_h'] * SS
    skin = identity['skin']
    # shoulders / clothes and neck
    d.ellipse([cx - 330 * SS, h * 0.80, cx + 330 * SS, h * 1.25], fill=identity['shirt'])
    d.rectangle([cx - 80 * SS, cy + fh * 0.35, cx + 80 * SS, h * 0.86], fill=tuple(int(c * 0.86) for c in skin))
    # hair behind head
    d.ellipse([cx - fw * 0.62, cy - fh * 0.72, cx + fw * 0.62, cy + fh * 0.40], fill=identity['hair'])
    # ears
    for sgn in (-1, 1):
        d.ellipse([cx + sgn * fw * 0.47 - 30 * SS, cy - 25 * SS, cx + sgn * fw * 0.47 + 30 * SS, cy + 75 * SS], fill=tuple(int(c * 0.92) for c in skin))
    # face (shaded)
    sh, mask = shade_ellipse((w, h), (cx - fw / 2, cy - fh / 2, cx + fw / 2, cy + fh / 2), skin, strength=0.42)
    bg.paste(sh, (0, 0), mask)
    d = ImageDraw.Draw(bg)
    # fringe
    d.pieslice([cx - fw * 0.55, cy - fh * 0.66, cx + fw * 0.55, cy - fh * 0.02], 180, 360, fill=identity['hair'])
    ey = cy - fh * 0.08
    sep = fw * identity['eye_sep']
    for sgn in (-1, 1):
        ex = cx + sgn * sep
        ew, eh = identity['eye_w'] * SS, identity['eye_h'] * SS
        d.ellipse([ex - ew, ey - eh, ex + ew, ey + eh], fill=(246, 244, 240))
        ir = eh * 0.95
        d.ellipse([ex - ir, ey - ir, ex + ir, ey + ir], fill=identity['iris'])
        pr = ir * 0.45
        d.ellipse([ex - pr, ey - pr, ex + pr, ey + pr], fill=(10, 10, 12))
        d.ellipse([ex - ir * 0.55, ey - ir * 0.75, ex - ir * 0.2, ey - ir * 0.4], fill=(255, 255, 255))
        d.arc([ex - ew, ey - eh, ex + ew, ey + eh], 190, 350, fill=(40, 28, 24), width=int(4 * SS))          # upper lid
        d.line([ex - ew * 1.05, ey - eh * 2.0 - sgn * 6 * SS, ex + ew * 1.05, ey - eh * 2.35 + sgn * 6 * SS], fill=identity['hair'], width=int(11 * SS))  # brow
    # nose
    nx0 = cx
    d.polygon([(nx0, ey + 10 * SS), (nx0 - 34 * SS, cy + fh * 0.17), (nx0 + 34 * SS, cy + fh * 0.17)], fill=tuple(int(c * 0.92) for c in skin))
    d.ellipse([nx0 - 30 * SS, cy + fh * 0.13, nx0 - 10 * SS, cy + fh * 0.18], fill=tuple(int(c * 0.6) for c in skin))
    d.ellipse([nx0 + 10 * SS, cy + fh * 0.13, nx0 + 30 * SS, cy + fh * 0.18], fill=tuple(int(c * 0.6) for c in skin))
    # mouth
    my = cy + fh * 0.31
    mw = identity['mouth_w'] * SS
    d.pieslice([cx - mw, my - 28 * SS, cx + mw, my + 34 * SS], 5, 175, fill=(150, 52, 58))
    d.arc([cx - mw, my - 30 * SS, cx + mw, my + 34 * SS], 5, 175, fill=(90, 28, 32), width=int(4 * SS))
    img = bg.resize((W, H), Image.LANCZOS)
    # camera-ish look: tilt, light variation, blur and noise
    img = img.rotate(identity['tilt'] + r.uniform(-4, 4), resample=Image.BICUBIC, fillcolor=identity['bg_bottom'])
    arr = np.asarray(img, float) * r.uniform(0.9, 1.08)
    arr += np.random.RandomState(identity['seed'] * 31 + variant).normal(0, 3.0, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype('uint8')).filter(ImageFilter.GaussianBlur(0.8))


def page(lines, W=1240, H=1754, title='SAMPLE DOCUMENT'):
    img = Image.new('RGB', (W, H), (252, 252, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([60, 60, W - 60, 190], fill=(32, 62, 112))
    d.text((90, 95), title, font=font(60), fill=(255, 255, 255))
    y = 260
    for ln in lines:
        d.text((90, y), ln, font=font(40), fill=(20, 20, 24)); y += 74
    d.rectangle([90, y + 30, W - 90, y + 34], fill=(20, 20, 24))
    return img.filter(ImageFilter.GaussianBlur(0.4))


def scene(kind, W=1600, H=1066):
    r = random.Random(hash(kind) & 0xffff)
    if kind == 'mountains':
        img = grad(W, H, (110, 170, 230), (250, 220, 190)); d = ImageDraw.Draw(img)
        d.ellipse([W * 0.7, H * 0.12, W * 0.7 + 150, H * 0.12 + 150], fill=(255, 238, 170))
        for i, col in enumerate([(70, 90, 120), (50, 70, 95), (30, 50, 70)]):
            pts = [(0, H)]
            for x in range(0, W + 80, 80): pts.append((x, H * (0.55 + 0.1 * i) - r.uniform(0, 160)))
            pts.append((W, H)); d.polygon(pts, fill=col)
    elif kind == 'city':
        img = grad(W, H, (20, 24, 56), (210, 120, 90)); d = ImageDraw.Draw(img)
        x = 0
        while x < W:
            bw, bh = r.randint(60, 150), r.randint(200, 640)
            d.rectangle([x, H - bh, x + bw, H], fill=(18, 18, 30))
            for wy in range(H - bh + 20, H - 20, 36):
                for wx in range(x + 10, x + bw - 14, 26):
                    if r.random() < 0.5: d.rectangle([wx, wy, wx + 12, wy + 18], fill=(255, 220, 120))
            x += bw + 6
    else:  # sea
        img = grad(W, H, (130, 190, 240), (30, 90, 150)); d = ImageDraw.Draw(img)
        d.rectangle([0, H * 0.55, W, H], fill=(20, 80, 140))
        for i in range(40):
            y = H * 0.56 + i * 11; x = r.randint(0, W); d.arc([x, y, x + 260, y + 20], 0, 180, fill=(210, 235, 250), width=3)
        d.pieslice([W * 0.4, H * 0.50, W * 0.4 + 220, H * 0.50 + 200], 180, 360, fill=(255, 205, 120))
    return img.filter(ImageFilter.GaussianBlur(0.8))


def exif_bytes(dt, lat=None, lon=None, make='SyntheticCam', model='TestModel-1'):
    ex = Image.Exif()
    ex[0x010F] = make; ex[0x0110] = model; ex[0x0132] = dt
    ifd = ex.get_ifd(0x8769); ifd[0x9003] = dt; ifd[0x9004] = dt; ifd[0x829A] = (1, 125); ifd[0x829D] = (28, 10); ifd[0x8827] = 200
    if lat is not None:
        g = ex.get_ifd(0x8825)
        def dms(v): v = abs(v); d_ = int(v); m = int((v - d_) * 60); s = round((v - d_ - m / 60) * 3600 * 100); return (IFDRational(d_, 1), IFDRational(m, 1), IFDRational(s, 100))
        g[1] = 'N' if lat >= 0 else 'S'; g[2] = dms(lat); g[3] = 'E' if lon >= 0 else 'W'; g[4] = dms(lon)
    return ex


IDS = {
    'A': dict(seed=11, skin=(224, 178, 150), hair=(52, 34, 24), shirt=(40, 80, 150), iris=(70, 110, 60), bg_top=(120, 150, 190), bg_bottom=(190, 200, 210), face_w=430, face_h=560, eye_sep=0.23, eye_w=34, eye_h=15, mouth_w=62, tilt=0),
    'B': dict(seed=22, skin=(150, 104, 80), hair=(20, 16, 14), shirt=(150, 50, 60), iris=(60, 40, 30), bg_top=(200, 190, 150), bg_bottom=(120, 140, 120), face_w=470, face_h=590, eye_sep=0.26, eye_w=38, eye_h=17, mouth_w=70, tilt=2),
    'C': dict(seed=33, skin=(240, 205, 180), hair=(214, 170, 86), shirt=(60, 110, 90), iris=(60, 110, 170), bg_top=(90, 100, 130), bg_bottom=(170, 160, 150), face_w=410, face_h=540, eye_sep=0.24, eye_w=32, eye_h=14, mouth_w=58, tilt=-2),
}
plan = []
# (file, kind, identity, builder, date, gps)
for ident, n in (('A', 3), ('B', 2), ('C', 1)):
    for v in range(n):
        plan.append((f'portrait_{ident}{v + 1}.jpg', 'face', ident, ('face', ident, v), f'2026-10-{10 + len(plan):02d} 1{len(plan) % 9}:15:00', None))
plan += [
    ('document_invoice.jpg', 'document', None, ('page', ['INVOICE NO. 2026-0042', 'DATE: 2026-10-21', 'CUSTOMER: EXAMPLE TEST COMPANY', 'ITEM  WIDGET SAMPLE       QTY 12', 'ITEM  SERVICE SAMPLE      QTY 3', 'TOTAL AMOUNT: 1234.56 EUR'], 'SAMPLE INVOICE'), '2026-10-21 09:30:00', None),
    ('document_notice.jpg', 'document', None, ('page', ['MEETING NOTICE', 'ROOM: TEST ROOM 7', 'TIME: 14:00 - 15:30', 'AGENDA: SYNTHETIC DATA CHECK', 'CONTACT: NOBODY EXAMPLE'], 'NOTICE'), '2026-10-22 10:00:00', None),
    ('document_table.png', 'document', None, ('page', ['QUARTERLY REPORT Q3', 'REGION NORTH   1200   1350', 'REGION SOUTH   980    1010', 'REGION EAST    1500   1480', 'TOTAL          3680   3840'], 'SAMPLE REPORT'), None, None),
    ('scene_mountains.jpg', 'scene', None, ('scene', 'mountains'), '2026-09-14 12:00:00', (43.5081, 16.4402)),
    ('scene_city.jpg', 'scene', None, ('scene', 'city'), '2026-09-15 21:10:00', (45.8150, 15.9819)),
    ('scene_sea.jpg', 'scene', None, ('scene', 'sea'), '2026-09-16 08:40:00', (48.8566, 2.3522)),
]
manifest = []
for fn, kind, ident, spec, dt, gps in plan:
    if spec[0] == 'face': img = face(IDS[spec[1]], spec[2])
    elif spec[0] == 'page': img = page(spec[1], title=spec[2])
    else: img = scene(spec[1])
    path = OUT / fn
    dts = (dt or '2026-10-01 00:00:00').replace('-', ':', 2)
    if fn.endswith('.png'): img.save(path, 'PNG')
    else: img.save(path, 'JPEG', quality=90, exif=exif_bytes(dts, *(gps or (None, None))))
    manifest.append({'file': fn, 'kind': kind, 'identity': ident, 'width': img.width, 'height': img.height, 'has_exif': not fn.endswith('.png'), 'exif_date': dt, 'gps': gps, 'bytes': path.stat().st_size})
(OUT / 'manifest.json').write_text(json.dumps({'seed': SEED, 'files': manifest}, indent=1))
print(json.dumps({'count': len(manifest), 'total_bytes': sum(m['bytes'] for m in manifest)}))
