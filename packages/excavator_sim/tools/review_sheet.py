#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评审拼图：把参考照片和渲染图并排放，方便逐项核对轮廓。

参考照片来自 D:/Private data/AI/References/Robotics/Excavator-realism-20261107/
（小松 PC210LC-11，20 t 级同级参考）。**只读、只在本地内存里缩放，不复制、
不写进仓库、不进 release bundle** —— 这些照片没有分发权，也不该让人把渲染图
跟它们做像素级比对（透视投影 + 不同机型）。

    python3 tools/review_sheet.py                       # -> build/review/sheet.png
    python3 tools/review_sheet.py --ref-dir <目录>
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, pkg)
sys.path.insert(0, os.path.join(pkg, "tools"))
from excavator_sim import design as D                # noqa: E402
from excavator_sim.kinematics import fk             # noqa: E402
from excavator_sim.motion import STATIC_POSES       # noqa: E402

VIEWS = ("side", "q34", "top")
POSE_ORDER = ("transport", "park", "dig", "lift")
MEASURE_POSE = "park"

BG = (26, 32, 42)
FG = (208, 218, 232)
DIM = (140, 152, 170)
ACC = (232, 186, 74)
REF_BG = (245, 245, 245)

TITLE = "excavator_sim - normalized estimates, not OEM measurements"
SUB = ("geometry: normalized from public dimensions + photo chord normalization of a "
       "PC210LC-11 class machine; NOT a survey of the LiuGong 922")

REAR_LINKS = ("counterweight", "house_deck", "house_engine", "handrail",
              "cab_frame", "cab_trim", "cab_glass")
CAB_LINKS = ("cab_frame", "cab_trim", "cab_glass")


def _font(size):
    """默认位图字体太小；新版 Pillow 支持 load_default(size=)。"""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _collect(urdf, angles):
    """按 link 分组的世界坐标顶点（只用于测量，不渲染）。"""
    import preview_render as PR

    pose = urdf.forward_kinematics(PR.with_cylinders(angles))
    out = {}
    for link, items in urdf.visuals.items():
        if link not in pose:
            continue
        lr, lt = pose[link]
        chunks = []
        for fn, xyz, rpy, _rgb in items:
            if not os.path.exists(fn):
                continue
            v, _f = PR.load_obj(fn)
            local = v @ PR.rpy_matrix(*rpy).T + np.asarray(xyz, float)
            chunks.append(local @ lr.T + lt)
        if chunks:
            out[link] = np.concatenate(chunks)
    return out


def _measure(urdf):
    """park 姿态下的剪影尺寸。

    全部按**总长 = 1.000** 归一化。这些是从本模型顶点上量的，不是 OEM 数据；
    参考照片只用来定轮廓比例，照片带透视，做不了像素级标定。
    """
    ang = STATIC_POSES[MEASURE_POSE]
    lp = _collect(urdf, ang)
    if not lp:
        return None, []

    allp = np.concatenate(list(lp.values()))
    x0, x1 = float(allp[:, 0].min()), float(allp[:, 0].max())
    z1 = float(allp[:, 2].max())
    L = x1 - x0

    # URDF 里 link 名都带 "_link" 后缀（counterweight_link / cab_frame_link…），
    # 分组按去掉后缀的基名匹配，否则一条都匹配不上、量出来全是 0。
    def base(name):
        return name[:-5] if name.endswith("_link") else name

    rear = [p for k, p in lp.items() if base(k) in REAR_LINKS]
    r_tail = float(np.max(np.hypot(
        np.concatenate(rear)[:, 0], np.concatenate(rear)[:, 1]))) if rear else 0.0

    cab = [p for k, p in lp.items() if base(k) in CAB_LINKS]
    cab_h = float(np.concatenate(cab)[:, 2].max()) - D.HOUSE_Z if cab else 0.0

    trk = [p for k, p in lp.items() if k.startswith("track_")]
    trk_w = float(np.ptp(np.concatenate(trk)[:, 1])) if trk else 0.0

    # 动臂：弦 = 脚销→臂头销，弓高 = 动臂顶点到弦线的最大垂直距离
    pts = fk(ang)
    P0, P1 = np.array(pts["boom_pivot"]), np.array(pts["boom_head"])
    chord = float(np.linalg.norm(P1 - P0))
    bow = 0.0
    boom_pts = [p for k, p in lp.items() if base(k) == "boom"]
    if boom_pts:
        bv = np.concatenate(boom_pts)
        rel = bv - P0
        d = P1 - P0
        d /= np.linalg.norm(d)
        perp = rel - np.outer(rel @ d, d)
        bow = float(np.linalg.norm(perp, axis=1).max())

    rows = [
        ("overall length  (x)", 1.000),
        ("overall height  (z)", (z1 - float(allp[:, 2].min())) / L),
        ("tail swing radius", r_tail / L),
        ("cab height above deck", cab_h / L),
        ("track overall width (y)", trk_w / L),
        ("boom chord  foot->head pin", chord / L),
        ("boom bow (max off-chord)", bow / L),
        ("arm length (chord)", D.ARM_LEN / L),
    ]

    pins = []
    for name in ("boom_pivot", "boom_head", "arm_head", "bucket_lug",
                 "bucket_rim", "tooth_tip", "arm_back"):
        p = pts[name]
        pins.append((name, (p[0] - x0) / L, p[2] / L))

    return rows, pins



def _fit(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """等比缩放进 box，居中留白。"""
    s = min(box_w / img.width, box_h / img.height)
    im = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))),
                    Image.LANCZOS)
    canvas = Image.new("RGB", (box_w, box_h), BG)
    canvas.paste(im, ((box_w - im.width) // 2, (box_h - im.height) // 2))
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview", default=os.path.join(pkg, "build", "preview"))
    ap.add_argument("--out", default=os.path.join(pkg, "build", "review"))
    ap.add_argument("--ref-dir",
                    default=r"D:/Private data/AI/References/Robotics/"
                            r"Excavator-realism-20261107")
    ap.add_argument("--tile-w", type=int, default=700)
    ap.add_argument("--tile-h", type=int, default=480)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    tw, th = args.tile_w, args.tile_h
    # 参考行：两张照片 + 一段说明
    ref_h = 360
    ref_names = ["pc210lc-11_factory.png", "pc210lc-11_action-2.png"]
    refs = []
    for n in ref_names:
        p = os.path.join(args.ref_dir, n)
        if os.path.exists(p):
            refs.append((n, Image.open(p).convert("RGB")))
        else:
            print("  (missing reference: %s)" % p)

    header_h = 64
    width = tw * len(VIEWS)
    meas_h = 250
    height = header_h + ref_h + th * len(POSE_ORDER) + meas_h
    sheet = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(sheet)

    d.text((12, 10), TITLE, fill=FG)
    d.text((12, 32), SUB, fill=DIM)

    # ---- 参考行 --------------------------------------------------------
    y = header_h
    n = max(len(refs), 1)
    cw = width // n
    for i, (name, im) in enumerate(refs):
        tile = _fit(im, cw, ref_h - 26)
        tile = Image.new("RGB", (cw, ref_h), BG)
        inner = _fit(im, cw - 8, ref_h - 30)
        tile.paste(inner, (4, 26))
        sheet.paste(tile, (i * cw, y))
        d.text((i * cw + 8, y + 6), "REFERENCE (local only) " + name, fill=DIM)
    if not refs:
        d.text((12, y + 10), "reference photos not found at %s" % args.ref_dir,
               fill=DIM)

    # ---- 姿态 × 视角矩阵 ------------------------------------------------
    for r, pose in enumerate(POSE_ORDER):
        a = STATIC_POSES[pose]
        tag = "%s / side   (boom %+.2f  arm %+.2f  bucket %+.2f)" % (
            pose, a["boom_joint"], a["arm_joint"], a["bucket_joint"])
        for c, view in enumerate(VIEWS):
            p = os.path.join(args.preview, "%s_%s.png" % (pose, view))
            if not os.path.exists(p):
                print("  (missing render: %s)" % p)
                continue
            img = Image.open(p).convert("RGB")
            sheet.paste(img.resize((tw, th), Image.LANCZOS),
                        (c * tw, header_h + ref_h + r * th))
            # 角度写在每行第一格里（贴在这个姿态的渲染图上沿），不再单独
            # 在右下角飘一块表 —— 那块会压在 lift/top 的图上。
            label = tag if c == 0 else "%s / %s" % (pose, view)
            d.text((c * tw + 8, header_h + ref_h + r * th + 6),
                   label, fill=FG)

    # ---- 归一化剪影测量与铰点 -------------------------------------------
    # REVIEW_BRIEF 要求把"量了什么"摊在评审图里，而不是只在数据里给结论：
    # 剪影尺寸 + 铰点位置，统一按总长归一化，并明确标注是估计值。
    import preview_render as PR
    try:
        urdf = PR.Urdf(os.path.join(pkg, "urdf", "excavator.urdf"))
        rows, pins = _measure(urdf)
    except Exception as exc:                       # 测量失败不该毁掉拼图
        rows, pins = None, []
        print("  (measurement failed: %s)" % exc)

    my = header_h + ref_h + th * len(POSE_ORDER)
    d.rectangle([0, my, width, height], fill=(20, 25, 33))
    d.line([0, my, width, my], fill=(70, 82, 100), width=1)
    f_t = _font(15)
    f_s = _font(13)
    d.text((12, my + 8),
           "SILHOUETTE + PINS  (" + MEASURE_POSE
           + " pose, normalized by overall length = 1.000)",
           fill=ACC, font=f_t)
    d.text((12, my + 28),
           "normalized estimates, not OEM measurements - measured on this model's "
           "vertices, not from a surveyed machine", fill=DIM, font=f_s)

    if rows:
        for i, (name, val) in enumerate(rows):
            d.text((16, my + 52 + i * 20), "%-28s %.3f" % (name, val),
                   fill=FG, font=f_s)
        d.text((16, my + 52 + len(rows) * 20 + 6),
               "x from tailmost point, z from ground plane",
               fill=DIM, font=f_s)
        px0 = width // 3
        d.text((px0, my + 52), "%-14s %7s %7s" % ("pin (world, norm.)", "x", "z"),
               fill=ACC, font=f_s)
        for i, (name, nx, nz) in enumerate(pins):
            d.text((px0, my + 72 + i * 20),
                   "%-14s %7.3f %7.3f" % (name, nx, nz), fill=FG, font=f_s)
        d.multiline_text(
            (px0 * 2, my + 52),
            "Pins are the model's kinematic joints\n"
            "(foot/head/lug/rim/tooth), in the same\n"
            "normalized frame as the silhouette.\n\n"
            "Reference photos are local-only:\n"
            "no distribution rights, perspective\n"
            "projection, and a different machine\n"
            "(PC210LC-11 class), so they set\n"
            "proportions at best.",
            fill=DIM, font=f_s, spacing=4)
        for name, val in rows:
            print("  %-28s %.3f" % (name, val))

    out = os.path.join(args.out, "sheet.png")
    sheet.save(out)
    print("sheet ->", out)
    print("poses:", ", ".join(POSE_ORDER))
    print("NOTE: reference photos stay local; build/ is git-ignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
