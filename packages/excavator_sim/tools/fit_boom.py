#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 design.py 的动臂弦（脚销→臂头）自动对齐到参考照片里的动臂中线上。

人工点像素太主观：动臂脚销常年被油缸、耳板、履带架挡住，一像素的偏差经
5.7 m 弦放大后，上下缘偏距就全错了。这里改成用黄色掩膜算一个目标函数：

    score = mean(mask[弦中线]) - 0.55*mean(mask[上缘 +0.10 m])
                              - 0.55*mean(mask[下缘 -0.10 m])

即"中线落在机器黄上、上下缘外侧落在非黄上"。弦中线在 design 里近似就是
动臂局部中心线（根 Z≈-0.01，臂头 Z≈+0.055），所以这个目标等价于把弦
压在动臂中线上 —— 这正是 ref_overlay 量上下缘偏距之前必须做的一步。

搜索用坐标下降（脚销/臂头交替）+ 逐步减半的步长，4 次迭代足够收敛。
**输出仍然是归一化估计，不是 OEM 实测**；只用来给 ref_overlay 一个可信的弦。

    python tools/fit_boom.py IMAGE --foot 505,372 --head 215,148 [--tag fac]
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import design as D                      # noqa: E402
from ref_overlay import Projector, yellow_mask   # noqa: E402

# 参与打分的站位：跳过根部和臂头（根部紧挨上车/油缸，臂头上方是斗杆缸）
XS = np.arange(0.70, 5.45, 0.06)
TOP = np.interp(XS, D.BOOM_X, D.BOOM_TOP) + 0.10
BOT = np.interp(XS, D.BOOM_X, D.BOOM_BOT) - 0.10
ZERO = np.zeros_like(XS)


def _frac_yellow(mask, pr: Projector, Z: np.ndarray) -> float:
    """沿弦采样一组 Z 偏距，返回落在黄色掩膜里的比例（出界的算不黄）。"""
    h, w = mask.shape
    p = pr.pf[None, :] + pr.px_per_m * (XS[:, None] * pr.u[None, :] + Z[:, None] * pr.n[None, :])
    xi = np.round(p[:, 0]).astype(np.int32)
    yi = np.round(p[:, 1]).astype(np.int32)
    ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    if not ok.any():
        return 0.0
    return float(mask[yi[ok], xi[ok]].mean())


def score(mask, foot, head) -> float:
    pr = Projector(foot, head)
    return (_frac_yellow(mask, pr, ZERO)
            - 0.55 * _frac_yellow(mask, pr, TOP)
            - 0.55 * _frac_yellow(mask, pr, BOT))


def _descent(mask, foot, head, step, half):
    best = score(mask, foot, head)
    offs = np.arange(-half, half + 1e-9, step)
    for bank in (0, 1):
        improved = True
        while improved:
            improved = False
            cur = foot if bank == 0 else head
            for dx in offs:
                for dy in offs:
                    if dx == 0.0 and dy == 0.0:
                        continue
                    cand = (cur[0] + dx, cur[1] + dy)
                    sc = score(mask, cand if bank == 0 else foot,
                               head if bank == 0 else cand)
                    if sc > best + 1e-6:
                        best, cur, improved = sc, cand, True
            if bank == 0:
                foot = cur
            else:
                head = cur
    return foot, head, best


def fit(mask, foot, head, verbose=True):
    foot = tuple(float(v) for v in foot)
    head = tuple(float(v) for v in head)
    for step, half in ((8.0, 32.0), (4.0, 16.0), (2.0, 8.0), (1.0, 4.0), (0.5, 2.0)):
        foot, head, sc = _descent(mask, foot, head, step, half)
        if verbose:
            print("  step %.1f  foot=(%7.1f,%7.1f) head=(%7.1f,%7.1f)  score %+.3f"
                  % (step, foot[0], foot[1], head[0], head[1], sc))
    return foot, head, sc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--foot", default="505,372")
    ap.add_argument("--head", default="215,148")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args(argv)

    foot0 = tuple(float(v) for v in args.foot.split(","))
    head0 = tuple(float(v) for v in args.head.split(","))

    img = Image.open(args.image).convert("RGB")
    mask = yellow_mask(np.array(img))
    print("image %s  %dx%d  yellow %.1f%%"
          % (os.path.basename(args.image), img.width, img.height, 100.0 * mask.mean()))
    print("  start  foot=(%.1f,%.1f) head=(%.1f,%.1f)  score %+.3f"
          % (foot0[0], foot0[1], head0[0], head0[1], score(mask, foot0, head0)))

    foot, head, sc = fit(mask, foot0, head0)
    pr = Projector(foot, head)
    print("\nfitted chord %.1f px -> %.2f px/m  u=(%+.3f,%+.3f)"
          % (pr.chord_px, pr.px_per_m, pr.u[0], pr.u[1]))
    print("  --foot %d,%d --head %d,%d" % (round(foot[0]), round(foot[1]),
                                           round(head[0]), round(head[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
