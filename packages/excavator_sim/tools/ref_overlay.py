#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在参考照片上描动臂中心线/上下轮廓/铰点，并量出归一化剪影偏距。

REVIEW_BRIEF 第 25 行要求："Draw the centerline and pin locations over the
reference before changing the mesh." 这个脚本就是那一步：参考照片只读打开，
把 design.py 里的几何按"脚销→臂头"弦投影上去，图写到 build/review/。

投影约定（图像坐标 y 向下）：
    u = (p_head - p_foot) / |...|        弦方向，脚 → 臂头
    n = (-u.y, u.x)                      弦的上方法线（u 指左上时 n 指右上）
    s = |p_head - p_foot| / BOOM_LEN      px/m，用弦长消掉整体比例
    p(X, Z) = p_foot + s * (X*u + Z*n)   (X, Z) 是 boom_link 局部坐标

两种模式：
    --mode measure   只量：沿法线采样黄色掩膜，报各站位上下缘偏距（弦归一化）
    --mode design    只画：把 design.py 的上下缘/中心线/铰点投到照片上
    --mode both      两个都出，并画在同一张图上（默认）

**这些是估计值，不是 OEM 实测**：照片是透视投影，按弦长归一化仍有前缩和偏航
误差，图上会印这句免责声明。参考照片绝不能进公开仓库（REVIEW_BRIEF 第 21 行）。

依赖 numpy + Pillow（开发机用）。
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import design as D  # noqa: E402

REVIEW_DIR = os.path.join(PKG, "build", "review")

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size: int):
    for fn in FONT_CANDIDATES:
        if os.path.exists(fn):
            try:
                return ImageFont.truetype(fn, size)
            except OSError:
                continue
    return ImageFont.load_default()


def yellow_mask(rgb: np.ndarray) -> np.ndarray:
    """机器黄，按 HSV 色相判定。

    原来的绝对 RGB 阈值只圈得住"中间调"的那一条带子：动臂上表面被照到会洗白
    （b 冲到 150 以上）、下表面在阴影里（r-g 变负），两头全丢，量出来的臂厚
    只剩 0.28 m（实测应是 0.85~1.0 m）。色相不受明暗影响，才是对的判据。

    H 在 PIL 的 HSV 里是 hue*255/360，机器黄约 44~50°，取 25~41（35~58°）；
    S>0.30 排掉天空/雾面（S<0.07）和无彩灰；V>0.22 排掉纯黑阴影。
    树叶偏绿（hue≈60° 往上）会被 41 挡住。
    """
    hsv = np.array(Image.fromarray(rgb).convert("HSV"))
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return (h >= 25) & (h <= 41) & (s > 78) & (v > 55)


class Projector:
    """参考照片 → boom 局部坐标的双向映射。"""

    def __init__(self, foot, head, boom_len=D.BOOM_LEN, zoff=0.0):
        pf = np.array(foot, dtype=float)
        u = (np.array(head, dtype=float) - pf)
        self.chord_px = float(np.hypot(*u))
        u = u / self.chord_px
        self.n = np.array([-u[1], u[0]])                 # 上方法线
        self.px_per_m = self.chord_px / boom_len
        # zoff：把弦沿上方法线平移多少米。实机销线不在动臂截面中点上——
        # 量出来截面中心比销线高 0.15 m 左右，而弦是照"截面中心"画的。
        # 想把 design 的上下缘叠准，就把弦抬到销线上（zoff≈+0.14）。
        self.u = u
        self.pf = pf + zoff * self.px_per_m * self.n

    def to_px(self, X, Z):
        return self.pf + self.px_per_m * (X * self.u + Z * self.n)

    def sample(self, X, d):
        """沿法线偏移 d（米）后的像素坐标；X 是沿弦的局部坐标。"""
        return self.to_px(X, 0.0) + d * self.px_per_m * self.n


def _bridge(hits, max_gap):
    """把长度 ≤ max_gap 的 False 缝填上（一维闭运算）。

    动臂是一整块机器黄，但表面上印着 KOMATSU 白字、还有斜打的高光，掩膜会
    沿着法线切出一两条 5~10 cm 的缝。不桥接的话"包含 d=0 的那一段"就只剩缝
    下面那一小块，量出来的臂厚 0.3 m 全是假的。
    """
    out = list(hits)
    n = len(out)
    i = 0
    while i < n:
        if out[i]:
            i += 1
            continue
        j = i
        while j < n and not out[j]:
            j += 1
        if j - i <= max_gap and i > 0 and j < n:
            for k in range(i, j):
                out[k] = True
        i = j
    return out


def measure_edges(mask, pr: Projector, stations, half_span_m=0.70, step_m=0.004,
                  min_run_m=0.12, bridge_m=0.12):
    """沿弦法线找"跨过弦的那段黄色"，返回每站位的 (上缘偏距, 下缘偏距)，单位 m。

    不能取"最长连续段"：动臂根部紧挨着驾驶室顶棚，射线穿出动臂以后还会打在
    别的黄色件上，最长段反而跑偏。正确做法是取**包含 d=0 的那一段**。

    也**不能**在没有段包含 d=0 时退到"离 0 最近的段"——那是早期的写法，弦一旦
    落在动臂外面（角度偏 5° 就够），最近的那段就只是动臂边缘的一条高光棱，
    量出来的臂厚只有 0.3 m。现在改成直接报 None：没数据好过假数据。
    """
    out = []
    n_steps = int(half_span_m / step_m)
    ds = np.arange(-n_steps, n_steps + 1) * step_m
    h, w = mask.shape
    min_run = max(int(round(min_run_m / step_m)), 2)
    max_gap = int(round(bridge_m / step_m))
    for X in stations:
        hits = []
        for d in ds:
            p = pr.sample(X, d)
            x, y = int(round(p[0])), int(round(p[1]))
            hits.append(bool(0 <= x < w and 0 <= y < h and mask[y, x]))
        hits = _bridge(hits, max_gap)
        runs = []
        k = 0
        while k < len(hits):
            if hits[k]:
                j = k
                while j + 1 < len(hits) and hits[j + 1]:
                    j += 1
                if j - k >= min_run:
                    runs.append((k, j))
                k = j + 1
            else:
                k += 1
        k0 = n_steps  # d = 0 的下标
        hit = [r for r in runs if r[0] <= k0 <= r[1]]
        if not hit:
            out.append((None, None))
            continue
        run = hit[0]
        out.append((ds[run[1]], ds[run[0]]))   # +d 朝上 = 上缘
    return out


def draw_polyline(draw, pr: Projector, pts, color, width=3):
    xy = [tuple(pr.to_px(X, Z)) for X, Z in pts]
    if len(xy) >= 2:
        draw.line(xy, fill=color, width=width, joint="curve")


def draw_pin(draw, pr: Projector, X, Z, label, color, r=9, font=None, dy=-26):
    p = pr.to_px(X, Z)
    x, y = float(p[0]), float(p[1])
    draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=3)
    draw.line([x - r * 1.8, y, x + r * 1.8, y], fill=color, width=1)
    draw.line([x, y - r * 1.8, x, y + r * 1.8], fill=color, width=1)
    if label and font is not None:
        draw.text((x + r + 4, y + dy), label, fill=color, font=font)


def make_overlay(img, pr: Projector, masked, measured=None, stations=None,
                 show_design=True, title=""):
    base = img.convert("RGB").copy()
    # 黄色掩膜淡淡染一层，方便肉眼确认量到的是机器本体
    if masked is not None:
        tint = np.array(base, dtype=np.float32)
        m = masked
        tint[m] = tint[m] * 0.72 + np.array([40.0, 120.0, 60.0]) * 0.28
        base = Image.fromarray(tint.astype(np.uint8))

    draw = ImageDraw.Draw(base)
    f_pin = load_font(22)
    f_txt = load_font(20)
    f_big = load_font(26)

    # 弦 + 法线示例
    draw_polyline(draw, pr, [(0.0, 0.0), (D.BOOM_LEN, 0.0)],
                  (255, 90, 200), width=2)

    if show_design:
        # 上下缘
        draw_polyline(draw, pr, list(zip(D.BOOM_X, D.BOOM_TOP)), (60, 235, 255), 3)
        draw_polyline(draw, pr, list(zip(D.BOOM_X, D.BOOM_BOT)), (60, 235, 255), 3)
        # 中心线
        draw_polyline(draw, pr, D.BOOM_CL, (255, 60, 60), 3)
        # 物理销画圆圈 + 十字；kink 只是上缘斜率折点，不承力，画小三角，
        # 免得被当成第五个销孔。
        for key, dy in (("foot", 12), ("head", 12),
                        ("boom_cyl", 16), ("arm_cyl", -30)):
            X, Z = D.BOOM_PINS[key]
            draw_pin(draw, pr, X, Z, key, (255, 240, 80), r=8, font=f_pin, dy=dy)
        kx, kz = pr.to_px(*D.BOOM_PINS["kink"])
        draw.polygon([(kx, kz - 7), (kx + 8, kz + 6), (kx - 8, kz + 6)],
                     outline=(255, 176, 40), width=2)
        if f_pin is not None:
            draw.text((kx + 12, kz - 34), "kink", fill=(255, 176, 40), font=f_pin)
            draw.text((kx + 12, kz - 12), "(edge fold, not a pin)",
                      fill=(255, 176, 40), font=f_pin)

    if measured is not None and stations is not None:
        tops, bots = [], []
        for X, (tp, bt) in zip(stations, measured):
            if tp is None:
                tops.append(None)
                bots.append(None)
                continue
            tops.append(tuple(pr.to_px(X, tp)))
            bots.append(tuple(pr.to_px(X, bt)))
        for seq in (tops, bots):
            pts = [p for p in seq if p is not None]
            if len(pts) >= 2:
                draw.line(pts, fill=(255, 165, 0), width=3)
        for X, (tp, bt) in zip(stations, measured):
            if tp is None:
                continue
            for d in (tp, bt):
                p = pr.sample(X, d)
                draw.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3],
                             fill=(255, 165, 0))

    # 免责声明
    lines = [
        "normalized estimates, NOT OEM measurements",
        "perspective photo: chord-normalized, foreshortening remains",
        title,
    ]
    y0 = 12
    for i, t in enumerate(lines):
        if not t:
            continue
        draw.rectangle([8, y0 - 3, 12 + 14 * len(t), y0 + 30], fill=(20, 24, 30))
        draw.text((14, y0), t, fill=(255, 210, 120), font=f_big if i == 0 else f_txt)
        y0 += 34
    return base


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--foot", required=True, help="脚销像素坐标 x,y")
    ap.add_argument("--head", required=True, help="臂头销像素坐标 x,y")
    ap.add_argument("--mode", choices=["measure", "design", "both", "none"], default="both")
    ap.add_argument("--stations", type=int, default=24)
    ap.add_argument("--half-span", type=float, default=0.70,
                    help="沿法线单侧采样半宽（米）。动臂弓形上凸时弦贴下缘，"
                         "上缘偏距会超过 0.7，需要加大到 1.3~1.5")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tag", default=None, help="输出文件名标签")
    ap.add_argument("--no-tint", action="store_true")
    ap.add_argument("--crop", default=None, help="裁剪并放大：x0,y0,x1,y1（原图坐标）")
    ap.add_argument("--zoom", type=float, default=2.0)
    ap.add_argument("--grid", type=int, default=0, help="每 N 像素画一条带坐标的网格")
    ap.add_argument("--zoff", type=float, default=0.0,
                    help="弦沿上方法线平移量（米）。量测用 0（弦在截面中心），"
                         "核对 design 上下缘时抬到销线上（约 +0.14）")
    args = ap.parse_args(argv)

    foot = tuple(float(v) for v in args.foot.replace(" ", "").split(","))
    head = tuple(float(v) for v in args.head.replace(" ", "").split(","))

    img = Image.open(args.image).convert("RGB")
    rgb = np.array(img)
    mask = yellow_mask(rgb)
    covered = 100.0 * mask.mean()
    pr = Projector(foot, head, zoff=args.zoff)

    tag = args.tag or os.path.splitext(os.path.basename(args.image))[0]
    os.makedirs(REVIEW_DIR, exist_ok=True)
    out = args.out or os.path.join(REVIEW_DIR, "overlay_%s.png" % tag)

    print("image %s  %dx%d" % (os.path.basename(args.image), img.width, img.height))
    print("chord %.1f px  ->  %.2f px/m   yellow %.1f%%"
          % (pr.chord_px, pr.px_per_m, covered))
    print("u=(%+.3f,%+.3f)  up-normal=(%+.3f,%+.3f)"
          % (pr.u[0], pr.u[1], pr.n[0], pr.n[1]))

    stations = [D.BOOM_LEN * (0.04 + 0.92 * i / (args.stations - 1))
                for i in range(args.stations)]
    measured = None
    if args.mode in ("measure", "both"):
        measured = measure_edges(mask, pr, stations, half_span_m=args.half_span)
        # design 同站位插值，和量测并排放，省得来回翻
        d_top = np.interp(stations, D.BOOM_X, D.BOOM_TOP)
        d_bot = np.interp(stations, D.BOOM_X, D.BOOM_BOT)
        print("\n  X(m)  t=X/L | meas_top  meas_bot   depth | desg_top  desg_bot   depth"
              " |  dTop   dBot")
        for X, (tp, bt), dt, db in zip(stations, measured, d_top, d_bot):
            if tp is None:
                print("  %5.2f  %5.2f |      --        --       -- | %+8.3f  %+8.3f  %7.3f |"
                      % (X, X / D.BOOM_LEN, dt, db, dt - db))
                continue
            print("  %5.2f  %5.2f | %+8.3f  %+8.3f  %7.3f | %+8.3f  %+8.3f  %7.3f "
                  "| %+5.3f  %+5.3f"
                  % (X, X / D.BOOM_LEN, tp, bt, tp - bt, dt, db, dt - db,
                     dt - tp, db - bt))

    def finish(im, path):
        """裁剪 + 放大（在原图坐标系画完再裁，避免坐标换算）。"""
        if args.grid:
            g = args.grid
            gd = ImageDraw.Draw(im)
            gf = load_font(13)
            for x in range(0, im.width, g):
                col = (255, 0, 255) if x % (g * 5) == 0 else (120, 120, 140)
                gd.line([(x, 0), (x, im.height)], fill=col, width=1)
                if x % (g * 5) == 0:
                    gd.text((x + 2, 2), str(x), fill=(255, 0, 255), font=gf)
            for y in range(0, im.height, g):
                col = (255, 0, 255) if y % (g * 5) == 0 else (120, 120, 140)
                gd.line([(0, y), (im.width, y)], fill=col, width=1)
                if y % (g * 5) == 0:
                    gd.text((2, y + 1), str(y), fill=(255, 0, 255), font=gf)
        if args.crop:
            x0, y0, x1, y1 = (int(float(v)) for v in args.crop.split(","))
            im = im.crop((x0, y0, x1, y1))
            z = max(args.zoom, 1e-3)
            im = im.resize((max(int(im.width * z), 1), max(int(im.height * z), 1)),
                           Image.LANCZOS)
        im.save(path)
        print("wrote", path)

    if args.mode in ("measure", "both"):
        # 只画量测结果的干净版，方便和 design 版对照
        clean = make_overlay(img, pr, None if args.no_tint else mask,
                             measured=measured, stations=stations,
                             show_design=False, title="MEASURED silhouette")
        finish(clean, out.replace(".png", "_measured.png"))

    if args.mode == "none":
        finish(img, out)
        return 0

    if args.mode in ("design", "both"):
        ov = make_overlay(img, pr, None if args.no_tint else mask,
                          measured=measured, stations=stations,
                          show_design=True,
                          title="design.py: cyan=edges red=centerline yellow=pins")
        finish(ov, out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
