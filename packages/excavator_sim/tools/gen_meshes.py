#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 excavator_sim 用的轻量 OBJ 网格（20 t 级履带液压挖掘机外形）。

视觉参考：小松 PC210LC-11（20 t 级，与柳工 922 同级）。**同级参考，不是柳工
922 的测绘复刻**；参考照片只在本机做对照，不进仓库、不进 release。

尺寸的单一来源是 design.py（tools/gen_meshes.py、tools/ref_overlay.py、
tools/validate_kinematics.py 共用）。这里不再自己维护一套常量 —— 上一版就是
因为本文件另写了一份配重/铲斗耳板/油缸长度，和 design.py、cylinders.py 悄悄
漂移了（配重顶 1.34 vs 1.46、bucket rod 1.22 vs 1.25）。

    履带总长          4.45 m      履带板宽        0.60 m
    轨距（中心距）    2.20 m      整机宽          2.80 m
    司机室顶高        ~2.98 m     尾部回转半径    ~2.75 m
    动臂铰点          (1.15, 0, 1.02) m（house 系，离地 2.00 m）
    动臂长            5.70 m      斗杆长          2.95 m
    铲斗宽            1.40 m      五齿

所有顶点都是这个脚本现算的，没有复制任何第三方模型。

建模思路：
  * 动臂 / 斗杆 / 铲斗：沿 x 的上下缘轮廓（design.py 量出来的）做**变截面放样**
    （loft），截面是倒角八边形，半宽逐站变化 —— 这样侧影是一个连续箱型梁，
    不是若干块叠起来的板。
  * 配重：俯视 XY 圆弧轮廓沿 z 放样 + 上下小倒角（真机后缘是竖直弧面，
    不是侧视半圆）。
  * 驾驶室：斜前风挡的封闭壳体，玻璃拆成前风挡 / 左右侧窗 / 后窗四块独立薄板。

用法（输出目录默认 ../urdf/meshes/）：

    python3 gen_meshes.py
    python3 gen_meshes.py --out /tmp/meshes
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import design as D  # noqa: E402

TAU = math.tau


# --------------------------------------------------------------------------
# 基础向量工具
# --------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    length = math.sqrt(_dot(a, a))
    if length < 1e-12:
        return (1.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


# --------------------------------------------------------------------------
# 网格容器
# --------------------------------------------------------------------------

class Mesh:
    """一个只装三角形的 mesh，输出成带平面法线的 OBJ。"""

    def __init__(self, name: str):
        self.name = name
        self.verts: list[tuple[float, float, float]] = []
        self.tris: list[tuple[int, int, int]] = []

    # -- 顶点 / 面 ------------------------------------------------------
    def add_vert(self, x: float, y: float, z: float) -> int:
        self.verts.append((x, y, z))
        return len(self.verts) - 1

    def add_tri(self, a: int, b: int, c: int) -> None:
        if a != b and b != c and a != c:
            self.tris.append((a, b, c))

    def add_quad(self, a: int, b: int, c: int, d: int) -> None:
        self.add_tri(a, b, c)
        self.add_tri(a, c, d)

    def _fix_winding(self, t0: int) -> None:
        """把 tris[t0:] 这段刚加进去的闭合面统一成"法线朝内"。

        extrude() 只在**输入轮廓是 CCW** 时给出朝内的面；轮廓写成 CW，六个
        面就整体翻过来朝外。同一个 Mesh 里一旦混了两种绕序，有向体积互相抵消，
        绕反的那几块在背面剔除下**直接消失**，而且不会报错 —— 铲斗的销座圆柱
        和两块耳板就是这么丢的：斗壳是 CW 挤出的，体积比圆柱大一个量级，把
        save() 的整体符号判定带成了正值，于是全模型不翻，圆柱被剔掉，侧视里
        斗背看着"浮"在臂头前面。

        逐图元归一化以后，save() 的整体翻面只需要处理"全部朝内 ⇒ 翻成朝外"
        这一种情况，任何一个图元写反都不会再静默丢面。
        """
        vol = 0.0
        for a, b, c in self.tris[t0:]:
            vol += _dot(self.verts[a], _cross(self.verts[b], self.verts[c]))
        if vol <= 0.0:                     # 已是朝内（或退化），不动
            return
        for k in range(t0, len(self.tris)):
            a, b, c = self.tris[k]
            self.tris[k] = (a, c, b)

    # -- 基础体 ---------------------------------------------------------
    def box(self, x0, x1, y0, y1, z0, z1) -> None:
        t0 = len(self.tris)
        # 每对坐标先排序再生成。绕序是写死的，一旦调用点把 x0/x1 写反
        # （比如两个由不同函数算出来的边界），8 个顶点会整体镜像，六个面
        # 的法线全部朝内 —— 表面被背面剔除，看到的是盒子的内部，而且会
        # 和相邻共面几何打 z-fighting。驾驶室顶棚就是这么烂掉的：x0 算成
        # 0.795、x1 算成 −0.415，渲染出来一片横条纹。排序后最坏只是位置
        # 摆错，不会静默翻面。
        x0, x1 = (x0, x1) if x0 <= x1 else (x1, x0)
        y0, y1 = (y0, y1) if y0 <= y1 else (y1, y0)
        z0, z1 = (z0, z1) if z0 <= z1 else (z1, z0)
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        i = [self.add_vert(*v) for v in p]
        faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
                 (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        for a, b, c, d in faces:
            self.add_quad(i[a], i[b], i[c], i[d])
        self._fix_winding(t0)

    def cylinder(self, p0, p1, radius, seg=18, caps=True) -> None:
        t0 = len(self.tris)
        axis = _sub(p1, p0)
        if _dot(axis, axis) < 1e-12:
            return
        w = _norm(axis)
        ref = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (1.0, 0.0, 0.0)
        u = _norm(_cross(w, ref))
        v = _cross(w, u)

        ring0, ring1 = [], []
        for k in range(seg):
            a = TAU * k / seg
            off = (u[0] * math.cos(a) + v[0] * math.sin(a),
                   u[1] * math.cos(a) + v[1] * math.sin(a),
                   u[2] * math.cos(a) + v[2] * math.sin(a))
            ring0.append(self.add_vert(p0[0] + radius * off[0],
                                       p0[1] + radius * off[1],
                                       p0[2] + radius * off[2]))
            ring1.append(self.add_vert(p1[0] + radius * off[0],
                                       p1[1] + radius * off[1],
                                       p1[2] + radius * off[2]))
        # 统一按"法线朝内"生成（和其它基础体一致），save() 里整体翻一次。
        for k in range(seg):
            j = (k + 1) % seg
            self.add_quad(ring0[j], ring0[k], ring1[k], ring1[j])
        if caps:
            c0 = self.add_vert(*p0)
            c1 = self.add_vert(*p1)
            for k in range(seg):
                j = (k + 1) % seg
                # 端盖绕序必须和侧壁一致（都朝内）。上一版这两行写成了
                # (c0, ring0[j], ring0[k])：侧壁朝内、端盖朝外，而 _fix_winding
                # 只能整体翻一个图元，翻完侧壁对了端盖又反了。结果是每个圆柱
                # 的两头在背面剔除下都是透明洞（回转支承端面、各销轴端面），
                # 而且不报错。validate_kinematics 的共享边绕序检查就是抓这个：
                # 同一条边被两个面同向使用 ⇒ 法线不一致。
                self.add_tri(c0, ring0[k], ring0[j])
                self.add_tri(c1, ring1[j], ring1[k])
        self._fix_winding(t0)

    def pipe(self, pts, radius, seg=10, caps=True) -> None:
        """沿折线生成**连续**管：每个站点建一个圆环，相邻环连成侧壁。

        和"逐段 cylinder"的区别在拐点：cylinder 每段自带一对端盖，段与段
        在折点处角度不连续，端盖在光照下是一圈亮斑 —— 动臂上缘的液压管
        用逐段做法会变成一排断开的短棒。这里内部站点的环平面取前后两段
        方向的角平分线（斜接），管壁是连续的。

        环的朝向用平行传输求，避免每个站点各自挑参考向量导致管子沿轴自转。
        """
        n = len(pts)
        if n < 2:
            return
        t0 = len(self.tris)
        dirs = []
        for i in range(n):
            if i == 0:
                d = _norm(_sub(pts[1], pts[0]))
            elif i == n - 1:
                d = _norm(_sub(pts[-1], pts[-2]))
            else:
                a = _norm(_sub(pts[i], pts[i - 1]))
                b = _norm(_sub(pts[i + 1], pts[i]))
                d = _norm(tuple(a[k] + b[k] for k in range(3)))
            dirs.append(d)

        ref = (1.0, 0.0, 0.0) if abs(dirs[0][0]) < 0.9 else (0.0, 0.0, 1.0)
        ref = _sub(ref, tuple(dirs[0][k] * _dot(dirs[0], ref) for k in range(3)))
        rings = []
        for i in range(n):
            d = dirs[i]
            if _dot(ref, ref) < 1e-9:
                alt = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
                ref = _sub(alt, tuple(d[k] * _dot(d, alt) for k in range(3)))
            u = _norm(ref)
            v = _cross(d, u)
            ref = u                                  # 平行传输到下一站
            p = pts[i]
            rings.append([self.add_vert(p[0] + radius * (u[0] * math.cos(a)
                                                        + v[0] * math.sin(a)),
                                        p[1] + radius * (u[1] * math.cos(a)
                                                        + v[1] * math.sin(a)),
                                        p[2] + radius * (u[2] * math.cos(a)
                                                        + v[2] * math.sin(a)))
                          for a in (TAU * k / seg for k in range(seg))])

        for i in range(n - 1):
            r0, r1 = rings[i], rings[i + 1]
            for k in range(seg):
                j = (k + 1) % seg
                self.add_quad(r0[j], r0[k], r1[k], r1[j])
        if caps:
            c0 = self.add_vert(*pts[0])
            c1 = self.add_vert(*pts[-1])
            for k in range(seg):
                j = (k + 1) % seg
                # 同 cylinder()：端盖跟着侧壁一起朝内，否则两头是透明洞。
                self.add_tri(c0, rings[0][k], rings[0][j])
                self.add_tri(c1, rings[-1][j], rings[-1][k])
        self._fix_winding(t0)

    def extrude(self, profile, y0, y1, cap0=True, cap1=True) -> None:
        """把 XZ 平面闭合轮廓沿 Y 从 y0 挤出到 y1。"""
        t0 = len(self.tris)
        tris = triangulate(profile)
        n = len(profile)
        front = [self.add_vert(x, y1, z) for (x, z) in profile]
        back = [self.add_vert(x, y0, z) for (x, z) in profile]
        if cap1:
            for a, b, c in tris:
                self.add_tri(front[a], front[b], front[c])
        if cap0:
            for a, b, c in tris:
                self.add_tri(back[c], back[b], back[a])
        for k in range(n):
            j = (k + 1) % n
            self.add_quad(back[k], back[j], front[j], front[k])
        self._fix_winding(t0)

    def ring_band(self, outer, inner, y0, y1) -> None:
        """两条等长的闭合轮廓之间的带状体（用于履带环）。"""
        t0 = len(self.tris)
        n = len(outer)
        assert n == len(inner)
        of = [self.add_vert(x, y1, z) for (x, z) in outer]
        inf = [self.add_vert(x, y1, z) for (x, z) in inner]
        ob = [self.add_vert(x, y0, z) for (x, z) in outer]
        inb = [self.add_vert(x, y0, z) for (x, z) in inner]
        for k in range(n):
            j = (k + 1) % n
            self.add_quad(of[k], of[j], inf[j], inf[k])
            self.add_quad(ob[j], ob[k], inb[k], inb[j])
            self.add_quad(ob[k], ob[j], of[j], of[k])
            self.add_quad(inf[k], inf[j], inb[j], inb[k])
        self._fix_winding(t0)

    # -- 输出 -----------------------------------------------------------
    def signed_volume(self) -> float:
        vol = 0.0
        for a, b, c in self.tris:
            vol += _dot(self.verts[a], _cross(self.verts[b], self.verts[c]))
        return vol / 6.0

    def flip(self) -> None:
        self.tris = [(a, c, b) for (a, b, c) in self.tris]

    def save(self, path: str, mtl: str) -> None:
        # 闭合网格的有向体积为负说明整块面朝里，统一翻一次。
        if self.signed_volume() < 0:
            self.flip()

        base = os.path.splitext(os.path.basename(path))[0]
        lines = [
            "# %s -- generated by gen_meshes.py, do not edit by hand" % base,
            "o %s" % base,
            "mtllib %s.mtl" % base,
            "usemtl %s" % mtl,
        ]
        for (x, y, z) in self.verts:
            lines.append("v %.5f %.5f %.5f" % (x, y, z))

        normals = []
        face_lines = []
        for a, b, c in self.tris:
            pa, pb, pc = self.verts[a], self.verts[b], self.verts[c]
            n = _norm(_cross(_sub(pb, pa), _sub(pc, pa)))
            normals.append(n)
            idx = len(normals)
            face_lines.append("f %d//%d %d//%d %d//%d" %
                              (a + 1, idx, b + 1, idx, c + 1, idx))

        for n in normals:
            lines.append("vn %.5f %.5f %.5f" % n)
        lines.extend(face_lines)

        with open(path, "w", encoding="ascii", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")

        mtl_path = os.path.join(os.path.dirname(path), base + ".mtl")
        with open(mtl_path, "w", encoding="ascii", newline="\n") as fh:
            fh.write("newmtl %s\nKa 0.2 0.2 0.2\nKd 0.7 0.7 0.7\n"
                     "Ks 0.1 0.1 0.1\nNs 20\nillum 2\n" % mtl)

    def stats(self) -> tuple[int, int]:
        return len(self.verts), len(self.tris)


# --------------------------------------------------------------------------
# 2D 多边形三角化（耳切法）
# --------------------------------------------------------------------------

def _area2(poly) -> float:
    s = 0.0
    n = len(poly)
    for k in range(n):
        x1, z1 = poly[k]
        x2, z2 = poly[(k + 1) % n]
        s += x1 * z2 - x2 * z1
    return s * 0.5


def _in_tri(p, a, b, c) -> bool:
    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])

    d1, d2, d3 = cross(a, b, p), cross(b, c, p), cross(c, a, p)
    has_neg = (d1 < -1e-9) or (d2 < -1e-9) or (d3 < -1e-9)
    has_pos = (d1 > 1e-9) or (d2 > 1e-9) or (d3 > 1e-9)
    return not (has_neg and has_pos)


def triangulate(poly):
    """返回 (a, b, c) 索引三元组，索引对应**调用者传进来的** poly 顺序。"""
    pts = list(poly)
    n_orig = len(pts)
    flipped = _area2(pts) < 0
    if flipped:
        pts.reverse()
    idx = list(range(len(pts)))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 5000:
        guard += 1
        n = len(idx)
        cut = False
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = pts[i0], pts[i1], pts[i2]
            cr = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if cr <= 1e-9:
                continue
            blocked = False
            for m in idx:
                if m in (i0, i1, i2):
                    continue
                if _in_tri(pts[m], a, b, c):
                    blocked = True
                    break
            if blocked:
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            cut = True
            break
        if not cut:
            break
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    if flipped:
        # pts 被反转后按 CCW 切耳，再把索引映射回调用者的原始顺序。
        #
        # 映射时必须**同时反转每个三角形的绕序**：反转点表只改了"点怎么编号"，
        # 没改几何。切出来的耳朵在反转表里是逆序前进的，映射回原表就变成了
        # 逆序倒退；而 extrude() 的侧壁是按原表正序连的。两者方向一致 ⇒ 共享边
        # 被两个面同向使用 ⇒ 背面剔除下这块盖板整个不显示。
        #
        # 上一版这里写的是 (n-1-a, n-1-b, n-1-c)，CCW 轮廓碰不到（不反转），
        # CW 轮廓必挂。铲斗斗背 outer+inner 的签名面积 = -0.217，正好是 CW：
        # 84 条"两侧绕序同向"全在 bucket.obj 上，就是这么来的。
        tris = [(n_orig - 1 - c, n_orig - 1 - b, n_orig - 1 - a)
                for (a, b, c) in tris]
    return tris


# --------------------------------------------------------------------------
# 轮廓工具
# --------------------------------------------------------------------------

def arc_pts(cx, cz, r, a0, a1, n):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n),
             cz + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def rounded_rect(x0, x1, z0, z1, r, seg=6):
    """圆角矩形轮廓（逆时针）。"""
    pts = []
    corners = [
        (x1 - r, z0 + r, -0.5 * math.pi, 0.0),
        (x1 - r, z1 - r, 0.0, 0.5 * math.pi),
        (x0 + r, z1 - r, 0.5 * math.pi, math.pi),
        (x0 + r, z0 + r, math.pi, 1.5 * math.pi),
    ]
    for cx, cz, a0, a1 in corners:
        pts.extend(arc_pts(cx, cz, r, a0, a1, seg)[:-1])
    return pts


def lerp_chain(a, b, n):
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
            for k in range(n + 1)]


def racetrack_pts(cx, cz, half_len, r, seg=10):
    """跑道形（两端半圆）闭合轮廓，逆时针。"""
    pts = []
    for k in range(seg + 1):
        a = -0.5 * math.pi + math.pi * k / seg
        pts.append((cx + half_len + r * math.cos(a), cz + r * math.sin(a)))
    for k in range(seg + 1):
        a = 0.5 * math.pi + math.pi * k / seg
        pts.append((cx - half_len + r * math.cos(a), cz + r * math.sin(a)))
    return pts


def _interp(x, xs, ys):
    """折线插值（xs 递增）；端点外取端点值。"""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + (ys[i] - ys[i - 1]) * t
    return ys[-1]


def _box_section(top, bot, hw, ch=0.045):
    """倒角八边形截面，返回 (u, v) = (y, z) 的逆时针点列。

    动臂/斗杆是焊接箱型梁：上下盖板比侧板略窄、四条棱角倒过。八边形足够
    表达这个形状，再细分对 rviz 的观感没有增益。
    """
    return [(-hw + ch, bot), (hw - ch, bot), (hw, bot + ch), (hw, top - ch),
            (hw - ch, top), (-hw + ch, top), (-hw, top - ch), (-hw, bot + ch)]


def _loft(m, axis, layers):
    """沿 axis 的变截面放样（闭合壳体）。

    axis = 0：每层是 (x, [(y, z), ...])，沿 +x 放样 —— 动臂 / 斗杆
    axis = 2：每层是 (z, [(x, y), ...])，沿 +z 放样 —— 配重 / 驾驶室

    上一版是"每段单独 extrude 再叠起来"：相邻两段在接缝处各有一对盖面，
    它们互相重叠却各自朝内，rviz 里看就是一段段套在一起的板。放样只留
    首尾两个盖，中间是连续侧壁，接缝处没有多余的面。

    绕序：本文件所有基础体（box/cylinder/extrude）都按**法线朝内**生成，
    由 Mesh.save() 按有向体积统一翻一次。这里保持同一约定，混用时才不会
    出现一半朝里一半朝外。所以截面必须是 CCW（(y,z) 或 (x,y) 平面），
    侧面用 (a[i], b[i], b[j], a[j])，低端盖正序、高端盖反序。
    """
    def pt(t, uv):
        if axis == 0:
            return (t, uv[0], uv[1])
        return (uv[0], uv[1], t)

    t0 = len(m.tris)
    rings = [[m.add_vert(*pt(t, p)) for p in uv] for t, uv in layers]

    n = len(rings[0])
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(n):
            j = (i + 1) % n
            m.add_quad(a[i], b[i], b[j], a[j])

    for tri in triangulate(list(layers[0][1])):
        i, j, k = tri
        m.add_tri(rings[0][i], rings[0][j], rings[0][k])
    last = len(layers) - 1
    for tri in triangulate(list(layers[last][1])):
        i, j, k = tri
        m.add_tri(rings[last][i], rings[last][k], rings[last][j])
    m._fix_winding(t0)


# --------------------------------------------------------------------------
# 尺寸常量：全部来自 design.py（单一来源）
# --------------------------------------------------------------------------
# 以前这里另写了一整套：导向轮 0.40 / 驱动轮 0.42（design 是 0.38）、
# 配重顶 1.34（design 是 1.46）、配重前缘 −1.02（design 是 −1.05）、
# 铲斗耳板 (0.30, 0.66)（design 是 (0.42, 0.50)）。改一处不改另一处，
# 网格和 URDF 就悄悄错开，所以现在只留别名，数值一律取 D.*。

IDLER_R = D.IDLER_R
SPROCKET_R = D.SPROCKET_R
TRACK_HALF = D.TRACK_HALF
TRACK_CZ = D.TRACK_CZ
TRACK_BELT_W = D.TRACK_BELT_W
TRACK_GAP = D.TRACK_GAP

HOUSE_Z = D.HOUSE_Z
BOOM_PIVOT = D.BOOM_PIVOT
BOOM_LEN = D.BOOM_LEN
ARM_LEN = D.ARM_LEN

# 履带环三层半径：内圈贴轮子、中间是链轨、最外是履带板外沿（= 接地面）。
# 上一版外圈 0.52 > 履带中心高 0.50，整条履带沉到地面以下 2 cm。
TRACK_R_IN = IDLER_R
TRACK_R_CHAIN = 0.46
TRACK_R_OUT = 0.50
TRACK_SHOE_T = 0.040                     # 履带板厚度（链轨外沿 → 接地）


# --------------------------------------------------------------------------
# 零件
# --------------------------------------------------------------------------

def gen_base_frame() -> Mesh:
    m = Mesh("base_frame")
    # 中央车架
    m.box(-1.05, 1.05, -0.62, 0.62, 0.40, 0.84)
    # 两侧纵梁，一直伸到履带架
    m.box(-0.95, 0.95, 0.58, 1.12, 0.50, 0.80)
    m.box(-0.95, 0.95, -1.12, -0.58, 0.50, 0.80)
    # 推土板（后部），20 t 挖机常见配置
    m.box(-1.62, -1.30, -0.70, 0.70, 0.10, 0.46)
    # 回转支承
    m.cylinder((0, 0, 0.84), (0, 0, 0.99), 0.78, seg=28)
    m.cylinder((0, 0, 0.99), (0, 0, 1.03), 0.62, seg=28)
    return m


def gen_track_belt() -> Mesh:
    m = Mesh("track_belt")
    half = TRACK_HALF
    outer = racetrack_pts(0.0, TRACK_CZ, half, TRACK_R_CHAIN, seg=12)
    inner = racetrack_pts(0.0, TRACK_CZ, half, TRACK_R_IN, seg=12)
    m.ring_band(outer, inner, -0.30, 0.30)
    return m


def gen_track_shoe() -> Mesh:
    """履带板：沿链轨外沿等距铺一圈，做出链轨的分节感。"""
    m = Mesh("track_shoe")
    half = TRACK_HALF
    pts = racetrack_pts(0.0, TRACK_CZ, half, TRACK_R_CHAIN, seg=12)
    # 重采样成等弧长点
    cum = [0.0]
    for k in range(len(pts)):
        j = (k + 1) % len(pts)
        cum.append(cum[-1] + math.hypot(pts[j][0] - pts[k][0],
                                        pts[j][1] - pts[k][1]))
    total = cum[-1]
    pitch = 0.165
    count = int(total / pitch)
    step = total / count

    def at(s):
        s %= total
        lo, hi = 0, len(cum) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if cum[mid] <= s:
                lo = mid
            else:
                hi = mid
        seg_len = cum[hi] - cum[lo] or 1e-9
        t = (s - cum[lo]) / seg_len
        p0, p1 = pts[lo], pts[hi % len(pts)]
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)

    for k in range(count):
        s = step * k
        p = at(s)
        q = at(s + 0.012)
        # 外法线 = 切向的右手法线。上一版用"由环心指向外侧"当法线：圆弧段
        # 还行，到了上下两条直段就变成 (0, ±1) 之外的斜向，履带板一片片歪着。
        tx, tz = q[0] - p[0], q[1] - p[1]
        tl = math.hypot(tx, tz) or 1e-9
        tx, tz = tx / tl, tz / tl
        nx, nz = tz, -tx
        # 切向半宽 0.46×步距 ⇒ 每块占 92% 步距、缝 8%（≈1.3 cm）。
        # 上一版 0.38 留了 24% 的缝，俯视 83 块连成一把梳子 —— 参考照片里
        # 相邻鞋板几乎贴死，只在铰接处一条细缝。缝不能为 0：留一点才能看出
        # 链轨是分节的，也留出多边形近似相邻块不互相穿插的余量。
        hw, hh = step * 0.46, TRACK_SHOE_T
        ax, az = p[0] + tx * hw, p[1] + tz * hw
        bx, bz = p[0] - tx * hw, p[1] - tz * hw
        quad = [(ax, az), (bx, bz),
                (bx + nx * hh, bz + nz * hh),
                (ax + nx * hh, az + nz * hh)]
        m.extrude(quad, -0.31, 0.31)
    return m


def gen_track_wheel() -> Mesh:
    """导向轮 / 驱动轮 / 履带架 / 托链轮 / 支重轮。

    轮子半径必须**小于**履带的链轨内圈。两个多边形近似（轮 seg=20、
    履带内圈 seg=12）在半径相同时会互相穿插：履带内圈多边形的边切进
    轮子表面，侧视里履带两端各冒出一个灰圆盘，看着像没装好。取 0.355
    —— 比内圈 0.38 小 2.5 cm，留出多边形近似的余量。
    """
    m = Mesh("track_wheel")
    r_wheel = 0.355
    # 前导向轮 / 后驱动轮
    m.cylinder((TRACK_HALF, -0.24, TRACK_CZ), (TRACK_HALF, 0.24, TRACK_CZ),
               r_wheel, seg=20)
    m.cylinder((-TRACK_HALF, -0.25, TRACK_CZ), (-TRACK_HALF, 0.25, TRACK_CZ),
               r_wheel, seg=20)
    # 履带架
    m.box(-1.32, 1.32, -0.21, 0.21, 0.44, 0.94)
    # 托链轮
    for x in (-0.62, 0.62):
        m.cylinder((x, -0.17, 0.90), (x, 0.17, 0.90), 0.10, seg=14)
    # 支重轮（下沿四个）
    for x in (-1.05, -0.35, 0.35, 1.05):
        m.cylinder((x, -0.19, 0.44), (x, 0.19, 0.44), 0.13, seg=14)
        m.cylinder((x, -0.19, 0.52), (x, 0.19, 0.52), 0.16, seg=14)
    return m


def gen_house_deck() -> Mesh:
    """上车平台（house 坐标：原点 = 回转中心，z 与 house_link 对齐）。"""
    m = Mesh("house_deck")
    # 侧视轮廓：前面有一级台阶，底面贴回转支承。后段被配重遮住，不用再做长
    prof = [
        (-1.10, 0.06), (1.22, 0.06), (1.22, 0.18),
        (0.92, 0.46), (-0.60, 0.46), (-0.60, 0.60),
        (-1.10, 0.60),
    ]
    m.extrude(prof, -1.15, 1.15)
    # 动臂铰点支座：从平台前缘顶起来，托住 (1.15, 1.02) 的动臂销
    m.box(0.58, 1.22, -0.26, 0.26, 0.44, 1.10)
    for sy in (-1, 1):
        # 两侧耳板，比中间厚出来一点，侧视时是道竖线
        m.box(0.58, 1.22, sy * 0.24, sy * 0.38, 0.30, 1.10)
    # 前部右上角的工作灯座
    m.box(1.05, 1.22, 0.60, 1.14, 0.46, 0.66)
    # 动臂缸缸底销支座：平台前缘往前探的鼻锥。
    # A 销在 house 系 (1.40, 0.10)（= cylinders.CYLINDERS["boom_cyl"]["A"]）。
    # 上一版没有这块，动臂缸的缸筒根部悬在平台前缘外看不见支点。
    ax, az = D.CYLINDERS["boom_cyl"]["A"]
    m.box(1.14, 1.50, -0.19, 0.19, az - 0.08, az + 0.16)
    for sy in (-1, 1):
        m.box(1.18, 1.48, sy * 0.13, sy * 0.21, az - 0.08, az + 0.14)
    m.cylinder((ax, -0.235, az), (ax, 0.235, az), 0.088, seg=16)
    # 右前缘挡板：把司机和动臂缸隔开。从 handrail_link 挪过来 —— 那是
    # 独立 link 用钢色材质，渲染出来是块孤立的灰白大板。
    m.box(1.10, 1.18, -1.18, 0.10, 0.46, 0.96)
    return m


def ctw_plan(inset: float, n: int = 20):
    """配重俯视轮廓（CCW）：前面一条直线 + 两段直侧壁 + 后缘一段大圆弧。

    整体内缩 inset：圆弧半径减 inset（弧心不动）、前沿 x 退到
    CTW_FRONT + inset、侧壁 y 收到 CTW_HALF_Y − inset。侧壁和圆弧的切点
    x 不用手写 —— 由"半径减多少、y 收到多少"反解，保证每一层都是相切的
    凸多边形，放样出来的侧面不会鼓包或内凹。

    上一版把圆弧画在 **xz** 平面里再沿 y 挤出 —— 等于把后缘做成了横放的
    圆柱，侧视看着圆滚滚、俯视却是个方屁股。REVIEW_BRIEF 第 2 项说的
    "counterweight 必须 XY 俯视后缘弧面"，指的就是这里。

    这一版又加了直侧壁：上一版弧从前沿直接起，R 只有 1.17 m，3/4 视整个
    后部都是连续弧面，读不出"侧板 + 圆弧"两段 —— 那才是"横放油桶"的来源。
    现在 R=1.50 m，侧壁 0.80 m 是平面，转角处法线突变，光照会断开。
    """
    r = D.CTW_R - inset
    xf = D.CTW_FRONT + inset
    hw = max(D.CTW_HALF_Y - inset, 1e-3)
    xs = D.CTW_CX - math.sqrt(max(r * r - hw * hw, 0.0))
    a0 = math.atan2(hw, xs - D.CTW_CX)       # 后弧起角，> 90°
    pts = [(xf, hw), (xs, hw)]
    # 弧从 (xs, +hw) 经最左点 (CX−r, 0) 绕到 (xs, −hw)；两端由侧壁给，跳过
    for k in range(1, n - 1):
        a = a0 + (TAU - 2.0 * a0) * k / (n - 1)
        pts.append((D.CTW_CX + r * math.cos(a), r * math.sin(a)))
    pts.append((xs, -hw))
    pts.append((xf, -hw))
    return pts


def gen_counterweight() -> Mesh:
    """配重：平底 + 竖直贴合面 + **俯视**后缘大圆弧，上下各一道小倒角。

    真机这三条一眼能认：① 侧视是一块近矩形的砣，顶面几乎水平；② 俯视后缘
    是连续大圆弧（回转半径 2.75 m）；③ z 向侧面近乎竖直，只在顶/底各收
    6~7 cm。所以沿 z 放样、每层用同一段俯视圆弧内缩 —— 不能用圆角矩形，
    更不能沿 y 挤出一个"横圆桶"。
    """
    m = Mesh("counterweight")
    _loft(m, 2, [(z, ctw_plan(inset)) for z, inset in D.CTW_LAYERS])
    return m


def gen_cab_frame() -> Mesh:
    """驾驶室骨架：底板 + 下裙 + 四根随玻璃后倾的立柱 + 顶棚 + 遮阳檐。

    偏置在机器左侧（+y）。前风挡上沿后倾 CAB_WINDSHIELD_RAKE、后窗
    CAB_REAR_RAKE —— 立柱必须跟着斜，否则玻璃贴着柱子的斜面会露出缝。

    玻璃只占上半截（CAB_SILL_TOP 以上），下半截是整块黄色钣金 —— 这条
    分界线是侧视里认出"驾驶室"而不是"一个黑盒子"的关键。
    """
    m = Mesh("cab_frame")
    x0, x1 = D.CAB_X0, D.CAB_X1
    y0, y1 = D.CAB_Y0, D.CAB_Y1
    z0 = D.CAB_Z0
    zs = D.CAB_SILL_TOP
    zg = D.CAB_GLASS_TOP
    z1 = D.CAB_Z1
    post = D.CAB_POST
    rake_f = D.CAB_WINDSHIELD_RAKE
    rake_r = D.CAB_REAR_RAKE

    def front_x(z):
        """z 处的驾驶室前表面 x（风挡以上后倾）。"""
        if z <= zs:
            return x1
        t = min((z - zs) / max(zg - zs, 1e-6), 1.0)
        return x1 - rake_f * t

    def rear_x(z):
        if z <= zs:
            return x0
        t = min((z - zs) / max(zg - zs, 1e-6), 1.0)
        return x0 + rake_r * t

    # 底板（比平台面高一点点，侧视里是道暗缝）
    m.box(x0, x1, y0, y1, z0, z0 + 0.14)
    # 下裙：从底板顶到窗台，实心黄板
    m.box(x0 + 0.02, x1 - 0.02, y0 + 0.02, y1 - 0.02, z0 + 0.14, zs)
    # 四根立柱：窗台以上随玻璃倾斜，用放样做，截面 CAB_POST 见方
    for cx, cy, sx_dir, sy_dir in ((front_x(zs), y0 + 0.02, -1, 0),
                                   (front_x(zs), y1 - 0.02 - post, -1, 0),
                                   (rear_x(zs), y0 + 0.02, +1, 0),
                                   (rear_x(zs), y1 - 0.02 - post, +1, 0)):
        layers = []
        for z in (zs, zg, z1 - 0.06):
            x = front_x(z) if sx_dir < 0 else rear_x(z)
            xa = x - (post if sx_dir < 0 else 0.0)
            xb = xa + post
            layers.append((z, [(xa, cy), (xb, cy),
                               (xb, cy + post), (xa, cy + post)]))
        _loft(m, 2, layers)
    # 顶棚：略微外挑，上表面平。
    # 前后边界分别从风挡/后窗的斜度算出来，前边界（≈0.80）比后边界
    # （≈−0.42）大 —— 直接按 (前, 后) 喂给 box 会让 x0 > x1，box 内部
    # 那六个面的绕序固定，宽度为负时整体镜像、法线全部朝内，顶棚就被
    # 背面剔除掉了（表现为顶棚消失、透过它看到窗框顶带，一片 z-fighting
    # 横条纹）。所以这里显式排序，别指望参数顺序。
    _fx = front_x(zg) - post - 0.03
    _rx = rear_x(zg) + post + 0.03
    m.box(min(_fx, _rx), max(_fx, _rx),
          y0 - 0.04, y1 + 0.04, zg, z1)
    # 前挡上沿的遮阳檐
    m.box(front_x(zg) + 0.02, front_x(zg) + 0.16, y0 + 0.02, y1 - 0.02,
          z1 - 0.10, z1 - 0.04)
    return m


def cab_glass_panels():
    """六块玻璃的角点（每块 = 一个四边形，逆时针看出去）。

    前风挡随 rake 后倾、左侧门窗在 CAB_DOOR_SPLIT 处断成两片、右侧一整片、
    后窗也后倾。返回 [(名字, [p0,p1,p2,p3]), ...]，p = (x, y, z)。
    玻璃必须贴着各自的面 —— 上一版是一整块黑 box 塞在柱子里，3/4 视下
    分不出窗和门，驾驶室就是个黑箱子。

    **侧窗的前/后边界必须跟着前后柱一起斜**：上一版侧窗是个竖直矩形，
    前边界固定在 x1-post，而后倾 0.40 m 的前柱一路退到 x1-rake_f，
    结果侧窗变成一块从车头悬出来的玻璃，侧视里驾驶室前缘还是垂直的
    —— 风挡后倾做了等于白做。现在侧窗是梯形：靠车头那片的上沿退到
    front_x(zg)-post，靠车尾那片的上沿跟着 rear_x(zg)+post 前移。
    """
    x0, x1 = D.CAB_X0, D.CAB_X1
    y0, y1 = D.CAB_Y0, D.CAB_Y1
    zs, zg = D.CAB_SILL_TOP, D.CAB_GLASS_TOP
    rake_f, rake_r = D.CAB_WINDSHIELD_RAKE, D.CAB_REAR_RAKE
    post = D.CAB_POST
    t = D.CAB_GLASS_T
    xi = x1 - t                       # 风挡玻璃内侧面
    xf = x1 - rake_f
    xri = x0 + t
    xr = x0 + rake_r
    # 侧窗靠前/靠后那两片的上沿 x：贴在对应立柱的内侧面上
    xf_side = x1 - rake_f - post      # 前柱上沿的内侧
    xr_side = x0 + rake_r + post      # 后柱上沿的内侧
    ya, yb = y0 + post, y1 - post     # 玻璃带的 y 范围（立柱之间）
    split = D.CAB_DOOR_SPLIT

    panels = [
        ("windshield", [(xi, ya, zs), (xi, yb, zs), (xf, yb, zg), (xf, ya, zg)]),
        ("rear", [(xri, ya, zs), (xr, ya, zg), (xr, yb, zg), (xri, yb, zs)]),
        ("left_front", [(x0 + post, y1 - t, zs), (split - post * 0.5, y1 - t, zs),
                        (split - post * 0.5, y1 - t, zg), (xr_side, y1 - t, zg)]),
        ("left_rear", [(split + post * 0.5, y1 - t, zs), (x1 - post, y1 - t, zs),
                       (xf_side, y1 - t, zg), (split + post * 0.5, y1 - t, zg)]),
        # 右侧同样断成两片：整片大窗在 3/4 视里是一整块深色面，分不出是玻璃
        # 还是没建模的空腔。左右都留 B 柱才像驾驶室。
        ("right_front", [(x0 + post, y0 + t, zs), (split - post * 0.5, y0 + t, zs),
                         (split - post * 0.5, y0 + t, zg), (xr_side, y0 + t, zg)]),
        ("right_rear", [(split + post * 0.5, y0 + t, zs), (x1 - post, y0 + t, zs),
                        (xf_side, y0 + t, zg), (split + post * 0.5, y0 + t, zg)]),
    ]
    return panels


def gen_cab_glass() -> Mesh:
    """玻璃：五块独立薄板（前风挡/后窗/左前/左后/右），每块沿自己的面法向加厚。

    不再用一整块 box —— 整块 box 的四个侧面会穿过立柱内表面，柱子看着像
    浮在玻璃里，而且右后角会从驾驶室外面透出来。
    """
    m = Mesh("cab_glass")
    for name, quad in cab_glass_panels():
        # 只给四边形加"厚度"：沿该面法向平移复制一组，再连成封闭壳
        p0, p1, p2, p3 = quad
        # 法向由前两点 + 第三点做叉积（面法向），归一到 0.03 m
        ax_, ay_, az_ = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        bx_, by_, bz_ = (p3[0] - p0[0], p3[1] - p0[1], p3[2] - p0[2])
        n = (ay_ * bz_ - az_ * by_, az_ * bx_ - ax_ * bz_, ax_ * by_ - ay_ * bx_)
        ln = math.sqrt(sum(c * c for c in n)) or 1e-9
        off = tuple(c / ln * D.CAB_GLASS_T for c in n)
        front = [m.add_vert(x + off[0], y + off[1], z + off[2]) for x, y, z in quad]
        back = [m.add_vert(x - off[0], y - off[1], z - off[2]) for x, y, z in quad]
        # 侧面（法线朝内，与文件其余基础体同一约定）
        for i in range(4):
            j = (i + 1) % 4
            m.add_quad(back[i], back[j], front[j], front[i])
        m.add_quad(front[0], front[1], front[2], front[3])
        m.add_quad(back[3], back[2], back[1], back[0])
    return m


def gen_cab_trim() -> Mesh:
    """驾驶室的黑色窗框：窗台带、顶带、左右 B 柱、门缝。深色件单独一个
    link —— rviz 每个 link 只认第一个 visual 的材质，多色必须拆 mesh。

    窗框必须**比玻璃外凸**：玻璃贴在立柱内侧，窗框如果和玻璃同面，
    正交渲染里两种深色连成一片，侧视就是一块没有分割的黑玻璃。
    """
    m = Mesh("cab_trim")
    x0, x1 = D.CAB_X0, D.CAB_X1
    y0, y1 = D.CAB_Y0, D.CAB_Y1
    z0 = D.CAB_Z0
    zs, zg = D.CAB_SILL_TOP, D.CAB_GLASS_TOP
    post = D.CAB_POST
    rake_f, rake_r = D.CAB_WINDSHIELD_RAKE, D.CAB_REAR_RAKE
    # 窗台带：绕一圈，压在玻璃下沿，比玻璃外凸 1 cm
    m.box(x0 + post, x1 - post, y0 + post * 0.4, y1 - post * 0.4,
          zs - 0.02, zs + 0.05)
    # 顶带：压在玻璃上沿，跟着后倾角度缩进
    m.box(x0 + rake_r + post, x1 - rake_f - post,
          y0 + post * 0.4, y1 - post * 0.4, zg - 0.045, zg)
    # 左右 B 柱（门窗分柱）。两侧都要有 —— 只做左边的话，从右前方 3/4 视
    # 看过去右窗还是一片没有分割的深色大面，读不出驾驶室。
    # 宽度 0.11 m（真机 B 柱 8~12 cm），外凸到车身外面 1 cm 才看得见。
    sp = D.CAB_DOOR_SPLIT
    m.box(sp - 0.055, sp + 0.055, y1 - 0.060, y1 + 0.010, zs, zg)
    m.box(sp - 0.055, sp + 0.055, y0 - 0.010, y0 + 0.060, zs, zg)
    # 门缝：从窗台一路落到下裙，侧视里把黄色下裙断开成"门 + 后侧板"。
    # 只做在车身外表面（2 cm 深），不影响内部。
    for yy, yy_in in ((y1, y1 - 0.02), (y0, y0 + 0.02)):
        ya, yb = sorted((yy, yy_in))
        m.box(sp - 0.012, sp + 0.012, ya, yb, z0 + 0.14, zs - 0.02)
    return m


def gen_house_engine() -> Mesh:
    """发动机罩 + 液压油箱：配重前面到驾驶室前柱那一段，平顶。

    侧视里这块必须是个带棱角的梯形箱体 —— 顶部一旦做成前后贯通的斜面，
    整个上车就会连成一颗胶囊，挖机轮廓立刻塌掉。
    """
    m = Mesh("house_engine")
    # 后沿必须顶到配重前脸（-1.40）里 2 cm，不能停在 -1.02：中间那 0.38 m
    # 在侧视里是一条竖直暗缝，看着像车身被切成两半。也不能正好 -1.40 ——
    # 两个面共面会 z-fighting，所以压进去 0.02。
    right = [(-1.42, 0.44), (0.34, 0.44), (0.30, 1.02),
             (0.06, 1.22), (-1.42, 1.22)]
    m.extrude(right, -1.12, 0.02)
    # 驾驶室背后左侧那一小段（同样顶到配重）
    left = [(-1.42, 0.44), (-0.54, 0.44), (-0.54, 1.20), (-1.42, 1.20)]
    m.extrude(left, 0.02, 1.12)
    # 顶部消声器 / 空滤凸台。底面必须压进机罩内部：上一版底面正好落在
    # z=1.22 与机罩顶面共面，正交光栅化时两个面交替通过深度测试，渲染出
    # 一片横条纹，看着像格栅其实是 z-fighting。
    m.box(-0.92, -0.48, -0.74, -0.06, 1.18, 1.37)
    # 右前上车的燃油箱 / 液压油箱：x 0.30…1.04、z 0.46…1.06 这一大片在侧视
    # 里原来是空的（只剩扶手和挡板两条细线，剪影缺一块）。真机那里是一个
    # 斜顶箱体，顶面比机罩低一截、前缘收一个角。y 只做到 −0.40，避开中间
    # 的动臂铰点支座（|y|<0.26），免得两块钱共面 z-fighting。
    tank = [(0.30, 0.46), (1.04, 0.46), (1.04, 0.86), (0.94, 1.06), (0.30, 1.06)]
    m.extrude(tank, -1.14, -0.40)
    # 加油口 / 呼吸阀凸台
    m.cylinder((0.78, -0.86, 1.05), (0.78, -0.86, 1.14), 0.072, seg=12)
    # 右侧上车踏步：两级，挂在平台侧沿外面
    for z in (0.31, 0.17):
        m.box(0.44, 0.72, -1.22, -1.06, z - 0.032, z + 0.032)
    return m


def gen_handrail() -> Mesh:
    """平台右前侧的扶手，侧面剪影里很显眼。

    以前这块 link 里还挂着一块 1.28 m 宽的"护板"，材质是 steel_light，
    结果 3/4 视里是一块孤零零立着的灰白大板，既不像护栏也不像钣金。
    真机那里是黄色挡板，已挪进 gen_house_deck（跟着车身配色）。
    """
    m = Mesh("handrail")
    for x in (0.05, 1.00):
        m.cylinder((x, -1.16, 0.62), (x, -1.16, 1.42), 0.025, seg=8)
    m.cylinder((0.05, -1.16, 1.42), (1.00, -1.16, 1.42), 0.025, seg=8)
    m.cylinder((0.05, -1.16, 1.02), (1.00, -1.16, 1.02), 0.020, seg=8)
    return m


def gen_boom() -> Mesh:
    """动臂：按实机上下缘逐站放样的箱型梁（坐标原点 = 动臂脚销）。

    上一版是"一条等厚的弯板"：上下缘用 8 个手调点连成的折线、宽度分 6 段
    梯形挤出，侧影是一根细长的铁棍，根部也没有明显的肩。

    这一版几何全部来自 design.BOOM_X/TOP/BOT/HW，也就是叠在 action-2 上
    量出来的那 12 个站位（tools/ref_overlay.py --zoff 0.14）。三条必须保住的
    辨识特征：
      1. 根部 X 0→0.7 截面陡然加深（0.70 → 0.86 m），侧影是一段鼓包；
      2. 上缘在 X≈1.1 的"肩"折平，之后一路缓降 —— 折点是直线折角，不是圆弧；
      3. 臂头铸件向下垂到销线以下约 0.31 m，靠一块圆头凸台收尾。
    这三点是"弓形观感"的来源，不是把中心线画成明显上凸（实测只鼓 0.15 m）。
    """
    m = Mesh("boom")
    _loft(m, 0, [(x, _box_section(t, b, hw)) for x, t, b, hw in
                 zip(D.BOOM_X, D.BOOM_TOP, D.BOOM_BOT, D.BOOM_HW)])
    # 脚销凸台：包住动臂销，侧影里是根部那个圆鼓
    m.cylinder((0.0, -0.30, 0.0), (0.0, 0.30, 0.0), 0.29, seg=22)
    # 臂头铸件：比主梁略收窄的圆头，包住斗杆销
    m.cylinder((5.65, -0.21, -0.03), (5.65, 0.21, -0.03), 0.20, seg=20)
    # 动臂缸杆端耳板（B = CYLINDERS["boom_cyl"]["B"]），左右各一对
    bx, bz = D.CYLINDERS["boom_cyl"]["B"]
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.24, sy * 0.47))
        m.box(bx - 0.18, bx + 0.19, y0, y1, bz - 0.17, bz + 0.16)
        m.cylinder((bx, y0, bz), (bx, y1, bz), 0.075, seg=14)
    # 斗杆缸缸头耳板（A = CYLINDERS["arm_cyl"]["A"]），立在上缘中部；
    # 这块缸在中面上，所以是一对夹在 y=0 两侧的耳板
    ax_, az_ = D.CYLINDERS["arm_cyl"]["A"]
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.055, sy * 0.105))
        m.box(ax_ - 0.16, ax_ + 0.16, y0, y1, az_ - 0.16, az_ + 0.09)
    m.cylinder((ax_, -0.115, az_), (ax_, 0.115, az_), 0.055, seg=14)
    return m


def gen_boom_pipe() -> Mesh:
    """动臂背面的液压管路：两根钢管 + 卡箍，顺着上缘棱角走。

    真机上这条明管沿动臂上表面一直铺到臂头，是辨认动臂走向的强特征，
    也让"上缘弧线"在纯色涂装下能读出来。

    z 由 BOOM_TOP 插值 + BOOM_PIPE_LIFT 得出，y 由 BOOM_HW 内收 0.075 得出
    —— 上一版把这两个值手抄成一张表，改完动臂截面后管有一半埋进箱体，
    有一半悬在空气里。
    """
    m = Mesh("boom_pipe")
    pts = []
    for x in D.BOOM_PIPE_X:
        pts.append((x,
                    _interp(x, D.BOOM_X, D.BOOM_HW),
                    _interp(x, D.BOOM_X, D.BOOM_TOP) + D.BOOM_PIPE_LIFT))
    for sy in (-1, 1):
        m.pipe([(x, sy * (hw - 0.075), z) for (x, hw, z) in pts],
               D.BOOM_PIPE_R, seg=10)
    # 卡箍：隔一个站位一只管夹，骑在上缘棱角上（间距太大管子会显得没固定）
    for x, hw, z in pts[1:-1:2]:
        for sy in (-1, 1):
            y0, y1 = sorted((sy * (hw - 0.06), sy * (hw + 0.015)))
            m.box(x - 0.03, x + 0.03, y0, y1,
                  z - D.BOOM_PIPE_R - 0.012, z + D.BOOM_PIPE_R + 0.012)
    return m


def gen_arm() -> Mesh:
    """斗杆：根部粗、头部收窄的箱型梁（坐标原点 = 斗杆根部铰点）。

    几何来自 design.ARM_X/TOP/BOT/HW，同样逐站放样。上一版是四段梯形挤出，
    相邻段在接缝处各留一对盖面，看起来像套在一起的四根管子。
    """
    m = Mesh("arm")
    _loft(m, 0, [(x, _box_section(t, b, hw)) for x, t, b, hw in
                 zip(D.ARM_X, D.ARM_TOP, D.ARM_BOT, D.ARM_HW)])
    # 根部叉板：跨在动臂臂头凸台（半宽 0.21）外侧，内缘不能小于 0.215
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.215, sy * 0.31))
        m.box(-0.13, 0.16, y0, y1, -0.22, 0.22)
    m.cylinder((0.0, -0.315, 0.0), (0.0, 0.315, 0.0), 0.13, seg=16)
    # 斗杆缸杆端耳板（B = CYLINDERS["arm_cyl"]["B"]），中面缸 ⇒ 两块夹板
    qx, qz = D.CYLINDERS["arm_cyl"]["B"]
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.055, sy * 0.11))
        m.box(qx - 0.14, qx + 0.14, y0, y1, qz - 0.10, qz + 0.10)
    m.cylinder((qx, -0.115, qz), (qx, 0.115, qz), 0.050, seg=14)
    # 铲斗缸缸头耳板（A = CYLINDERS["bucket_cyl"]["A"]）
    px, pz = D.CYLINDERS["bucket_cyl"]["A"]
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.055, sy * 0.105))
        m.box(px - 0.15, px + 0.16, y0, y1, pz - 0.15, pz + 0.10)
    m.cylinder((px, -0.11, pz), (px, 0.11, pz), 0.055, seg=14)
    # 臂头（铲斗销座）
    m.cylinder((D.ARM_LEN - 0.04, -0.19, 0.0), (D.ARM_LEN - 0.04, 0.19, 0.0),
               0.16, seg=16)
    # H-link 铰点耳板：斗杆头部两侧各一块，**夹在斗宽内侧**。
    # 上一版把 H 销架到 |y| 0.62…0.73（斗宽之外），3/4 视角看就是一个横跨
    # 整机的方框挂在工作装置末端 —— 真机连杆全部收在斗耳板中间，宽度约
    # 0.3 m。这里 H-link 板占 0.13…0.245，H 销跨 ±0.26 包住。
    hx, hz = D.H_LINK_PIN
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.13, sy * 0.245))
        m.box(hx - 0.13, hx + 0.13, y0, y1, hz - 0.16, hz + 0.07)
    m.cylinder((hx, -0.26, hz), (hx, 0.26, hz), 0.055, seg=12)
    return m


# 铲斗尺寸一律取 design.py，别在这里抄一遍（上一版这里写的是 (0.30, 0.66)，
# design 已经改成 (0.42, 0.50)，缸筒和斗耳板就在 rviz 里错开 0.2 m）。
BUCKET_CX, BUCKET_CZ = D.BUCKET_CX, D.BUCKET_CZ
BUCKET_R_OUT, BUCKET_R_IN = D.BUCKET_R_OUT, D.BUCKET_R_IN
BUCKET_A0, BUCKET_A1 = D.BUCKET_A0, D.BUCKET_A1
BUCKET_A_KNEE = D.BUCKET_A_KNEE
BUCKET_LUG = D.BUCKET_LUG
BUCKET_HALF_W = D.BUCKET_HALF_W
BUCKET_TEETH_Y = D.BUCKET_TEETH_Y

BUCKET_TOP_PLATE_LEN = 0.30      # 顶板从斗背顶端朝销轴方向伸出的长度


def _bk_pt(r, a):
    """斗腔圆弧上的点（bucket 局部 xz）。"""
    return (BUCKET_CX + r * math.cos(a), BUCKET_CZ + r * math.sin(a))


def _bk_chain(r, a_from, a_to, n=24):
    """斗壳轮廓点列：A_KNEE…A1 之间的角度走直线斗底板，其余走圆弧。

    路径方向由 a_from → a_to 决定（外轮廓 A0→A1 递减、内轮廓 A1→A0 递增），
    但**哪一段是直线只看角度落在哪个区间**，与遍历方向无关。上一版按
    "a_from → knee 走弧、knee → a_to 走直线"写，内轮廓就反了：直线段
    画到了 A1→knee 上，那段内弧 R=0.50 大于外弦到圆心的 0.482，内弧
    穿出外轮廓，端盖多边形自交，耳切切漏两块面。

    为什么要有折：186° 纯圆弧画出来的侧板是一个圆饼，正交平光下法线从
    +z 一路扫到 −x，没有一条硬边，3/4 视读成深色圆筒。折成弧+直线之后
    折点处有一条 41° 的硬棱，斗底板又是一整片受同一个法线的平面，
    侧影才读成 D 形。
    """
    knee = BUCKET_A_KNEE
    lo, hi = min(BUCKET_A1, knee), max(BUCKET_A1, knee)

    def _floor(a):        # 落在直线斗底板的角度区间
        return lo - 1e-9 <= a <= hi + 1e-9

    here, there = _floor(a_from), _floor(a_to)
    if here and there:        # 整段都在斗底板上
        return [_bk_pt(r, a_from), _bk_pt(r, a_to)]
    if here:                  # 起点在斗底板：先直着到折点，再沿弧走（内轮廓方向）
        return [_bk_pt(r, a_from)] + arc_pts(BUCKET_CX, BUCKET_CZ, r, knee, a_to, n - 1)
    if there:                 # 终点在斗底板：先沿弧到折点，再直着到底（外轮廓方向）
        return arc_pts(BUCKET_CX, BUCKET_CZ, r, a_from, knee, n - 1) + [_bk_pt(r, a_to)]
    return arc_pts(BUCKET_CX, BUCKET_CZ, r, a_from, a_to, n)     # 整段都在弧上


def bucket_top_plate(length=BUCKET_TOP_PLATE_LEN):
    """斗背顶板（销轴侧那块平板）的 2D 截面，沿 y 挤出。

    铲斗的口**不是整个敞开**的：销轴这一侧有一块顶板把两个侧板和斗壳焊在
    一起，斗腔的实际开口在顶板前缘与切削刃之间。少了这块板，3/4 俯视直接
    看进 C 形壳的内弧 —— 渲染出来就是一根开了口的深色圆管，这是上一版被
    判"铲斗像圆柱"的主因之一。

    截面从斗背顶端（外弧 + 内弧两个端点）朝销轴方向收 `length`：
    长 0.30 时外点 (-0.306,0.249) → (-0.073,0.059)，
    内点 (-0.204,0.185) → (0.029,-0.005)。
    板厚 = 内外弧半径差 0.12 m，方向指销轴，所以大面正好朝上（受光）。
    口开度因此留在 0.86 m，不至于挖不进去。

    `length` 是参数而不是常量，因为中央那一段要给 H-link 让位：H→P2 这条
    边从斗销上方扫到斗背外侧，斜着穿过顶板远端。中央段收到 0.12 m 之后
    整块板都落在 H-link 上方（见 gen_bucket）。
    """
    p_out = _bk_pt(BUCKET_R_OUT, BUCKET_A0)
    p_in = _bk_pt(BUCKET_R_IN, BUCKET_A0)
    rx, rz = -p_out[0], -p_out[1]                  # 从外点指向销轴（原点）
    r = math.hypot(rx, rz)
    dx, dz = length * rx / r, length * rz / r
    return [p_out, p_in,
            (p_in[0] + dx, p_in[1] + dz),
            (p_out[0] + dx, p_out[1] + dz)]


def gen_bucket() -> Mesh:
    """铲斗斗背（弧形壳 + 顶板）。坐标原点 = 铲斗销。

    斗背是绕销轴的一段圆弧：外弧 + 内弧夹出一层壳，开口（切削刃与顶板前缘
    之间的弦）朝向机器一侧 —— 反铲就是这么挖的。半径取 0.62 m（20 t 档
    斗深约 0.9 m），放大就成管子了。
    """
    m = Mesh("bucket")
    # 斗壳分三段挤出：两侧全宽环 + 中央一段。
    #
    # 中央段必须**上端开缺口**（148°→176°）并且顶板缩短（0.30→0.12）：
    # H-link 三角板的 H→P2 边从斗销正上方 (0.03, 0.26) 斜着扫到斗背后外侧
    # (-0.43, 0.02)，穿过斗背外壳 148°~172° 那一段和顶板远端。真机的斗背
    # 在这个位置本来就是开口的 —— 两块耳板立起来，板间没有壳。连杆全部
    # 收在 |y| < 0.28 里，所以只挖中央这一段，两侧斗宽照旧。
    LINK_GAP_HALF_W = 0.28
    LINK_GAP_ANG = math.radians(28)          # 148° → 176°
    outer = _bk_chain(BUCKET_R_OUT, BUCKET_A0, BUCKET_A1, 24)
    inner = _bk_chain(BUCKET_R_IN, BUCKET_A1, BUCKET_A0, 24)
    for sy in (-1, 1):
        y0, y1 = sorted((sy * LINK_GAP_HALF_W, sy * BUCKET_HALF_W))
        m.extrude(outer + inner, y0, y1)
        m.extrude(bucket_top_plate(), y0, y1)
    # 斗背横向加强筋。0.62 m 半径的弧面在正交平光下只剩法线渐变，
    # 没有筋板时 3/4 视角读成一根深色圆筒 —— 真机斗背外弧上本来就焊着
    # 几道横向筋板，这里补上，同时给斗背撑出结构感。筋板截面是弯的薄板，
    # 外凸 6 cm、内埋 1.5 cm，跨 ±0.58（不碰 ±0.63 起的侧板）。
    for adeg in (124.0, 100.0, 76.0, 52.0):
        a = math.radians(adeg)
        da = math.radians(6.0)
        band = (arc_pts(BUCKET_CX, BUCKET_CZ, BUCKET_R_OUT + 0.060,
                        a - da, a + da, 4)
                + arc_pts(BUCKET_CX, BUCKET_CZ, BUCKET_R_OUT - 0.015,
                          a + da, a - da, 4))
        m.extrude(band, -0.58, 0.58)
    # 切削刃板：斗壳在 -38° 收口，那一刀在真机上不是露出 0.12 m 厚的壳口，
    # 而是一条横贯整个斗宽的厚刃板。没有它，侧视里斗壳末端直接是一圈切面，
    # 和圆管端面没区别 —— 这是"铲斗像滚筒"的第二个来源。刃板沿切向朝斗口
    # 伸出 0.11 m、径向再薄 0.16 m 收成楔形，和斗齿座焊在一起。
    a1 = BUCKET_A1
    ux, uz = math.cos(a1), math.sin(a1)          # 径向（外壳法线）
    tx, tz = -math.sin(a1), math.cos(a1)         # 切向（朝斗壳本体）
    rim = _bk_pt(BUCKET_R_OUT, a1)

    def _blade(r_off, t_off):
        """r_off 沿径向往里、t_off 沿切向（+ 朝斗壳、− 朝斗口）。"""
        return (rim[0] - r_off * ux + t_off * tx,
                rim[1] - r_off * uz + t_off * tz)

    m.extrude([_blade(0.00, 0.02), _blade(0.00, -0.11),
               _blade(0.14, -0.11), _blade(0.14, 0.02)],
              -0.62, 0.62)
    # 中央段比两侧各宽 4 mm，避免两个端盖共面 z-fighting（重叠段全在实体内部）
    a0c = BUCKET_A0 + LINK_GAP_ANG
    outer_c = _bk_chain(BUCKET_R_OUT, a0c, BUCKET_A1, 14)
    inner_c = _bk_chain(BUCKET_R_IN, BUCKET_A1, a0c, 14)
    m.extrude(outer_c + inner_c, -LINK_GAP_HALF_W - 0.004,
              LINK_GAP_HALF_W + 0.004)
    m.extrude(bucket_top_plate(0.12), -LINK_GAP_HALF_W - 0.004,
              LINK_GAP_HALF_W + 0.004)
    # 销座：把斗背和铲斗销实心地连起来，否则侧视里斗背像是浮在臂头前面
    m.cylinder((0.0, -0.62, 0.0), (0.0, 0.62, 0.0), 0.20, seg=16)
    # dogbone 耳板：两块钢板立在斗背中央缺口的下沿（176°），从那里立到
    # BUCKET_LUG。上一版把耳板挂在 |y| 0.62…0.73（斗宽之外），和 H-link、
    # dogbone 一起做成一个横跨整机的外挂方框 —— 真机耳板间距约 0.2 m，
    # 收在斗宽里，dogbone 夹在它们外侧。
    lx, lz = BUCKET_LUG
    base = _bk_pt(BUCKET_R_OUT, a0c)      # 缺口下沿，(-0.398, -0.037)
    prof = [(lx - 0.09, lz + 0.06), (lx + 0.09, lz + 0.06),
            (base[0] + 0.09, base[1] - 0.01),
            (base[0] - 0.09, base[1] - 0.01)]
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.03, sy * 0.245))
        m.extrude(prof, y0, y1)
    m.cylinder((lx, -0.26, lz), (lx, 0.26, lz), 0.050, seg=12)
    return m


def gen_bucket_side() -> Mesh:
    """铲斗侧板：实心 D 形（外弧 → 口弦 → 顶板外沿），侧视里是一整片。

    侧板比斗壳外凸 7 cm（±0.63…±0.70），真机侧板就是焊在斗壳外侧的独立
    钢板。收口点从上一版的 (0.06,0.14) 改到顶板前缘 (-0.073,0.059)：这样
    侧板上缘和顶板外沿是一条线，不会在顶板前面留一段"断掉的边"。
    """
    m = Mesh("bucket_side")
    outer = _bk_chain(BUCKET_R_OUT, BUCKET_A0, BUCKET_A1, 18)
    prof = outer + [bucket_top_plate()[3]]        # 最后一点 = 顶板前缘外点
    # 外缘倒角：最外面 2 cm 收进 4.5%，侧视里就多出一圈硬边线。
    # 整块侧板在正交平光下是同一片纯色平面，不收边时读成一个圆盘；
    # 真机侧板外沿也是倒过角的（焊完打磨），不是一刀切齐的直棱。
    pcx = sum(p[0] for p in prof) / len(prof)
    pcz = sum(p[1] for p in prof) / len(prof)
    prof_o = [(pcx + (p[0] - pcx) * 0.955, pcz + (p[1] - pcz) * 0.955)
              for p in prof]
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.63, sy * 0.685))
        m.extrude(prof, y0, y1)
        y0, y1 = sorted((sy * 0.685, sy * 0.705))
        m.extrude(prof_o, y0, y1)
    # 刃口加强条：沿切削刃横过来一条厚板，比斗壳外弧再凸 3.5 cm
    #
    # 截面必须是个**有面积的矩形**。上一版四个角点是
    #     r_in·u, r_out·u, r_out·u − 0.13u, r_in·u − 0.13u
    # u 是径向单位向量 ⇒ 四个点全是 u 的倍数、也就是全在一条直线上，
    # 签名面积 = −1.4e-17。切耳算法一个三角形都切不出来，两端盖板根本不存在，
    # 只剩四条侧壁围成个空心"纸盒"，端面看过去是空的（validate_kinematics
    # 报的是 8 条"边被 1 个面使用"）。缺的是切向那一维宽度。
    a1 = BUCKET_A1
    ux, uz = math.cos(a1), math.sin(a1)          # 径向
    tx, tz = -math.sin(a1), math.cos(a1)         # 切向（沿刃口横移）
    r_lo, r_hi = BUCKET_R_OUT - 0.09, BUCKET_R_OUT + 0.035
    half = 0.055
    quad = [(BUCKET_CX + r * ux + s * tx, BUCKET_CZ + r * uz + s * tz)
            for r, s in ((r_lo, -half), (r_hi, -half),
                         (r_hi, half), (r_lo, half))]
    m.extrude(quad, -0.64, 0.64)
    return m


def _round_poly(pts, radii, seg=5):
    """多边形逐顶点圆角（二次贝塞尔近似），保持顶点顺序。

    pts 是 (x, z) 列表、闭合；radii 每顶点一个半径。返回值仍是闭合点列，
    但点变多了 —— extrude 的三角化能直接吃。半径必须小于两邻边长度，
    否则相邻圆角相互重叠、轮廓自交。
    """
    out = []
    n = len(pts)
    for i in range(n):
        p = pts[i]
        a, b = pts[i - 1], pts[(i + 1) % n]
        va = (a[0] - p[0], a[1] - p[1])
        vb = (b[0] - p[0], b[1] - p[1])
        la, lb = math.hypot(*va), math.hypot(*vb)
        r = radii[i]
        t1 = (p[0] + va[0] / la * r, p[1] + va[1] / la * r)
        t2 = (p[0] + vb[0] / lb * r, p[1] + vb[1] / lb * r)
        for k in range(seg + 1):
            t = k / seg
            u = 1.0 - t
            out.append((u * u * t1[0] + 2 * u * t * p[0] + t * t * t2[0],
                        u * u * t1[1] + 2 * u * t * p[1] + t * t * t2[1]))
    return out


def gen_h_link() -> Mesh:
    """H-link 三角板（双侧两片 + 三根横销）。局部原点 = H，+x 指向 P2。

    板上三个销的相对位置是刚性三角形的三条边：
        H  (0, 0)
        P2 (H_LINK_R2, 0)
        P1 (H_LINK_R1·cos GAM, H_LINK_R1·sin GAM) = (0, −0.46)

    中面 |y| 0.13…0.245，夹在斗耳板外侧、斗宽内侧。上一版放在 |y| 0.62…
    0.73（斗宽之外），3/4 视角就是一个横跨整机的方框；真机连杆全收在
    斗耳板之间，整束宽度约 0.3 m。H 销跨 ±0.26 把两块板穿起来。
    """
    m = Mesh("h_link")
    tri = [(0.0, 0.0),
           (D.H_LINK_R2, 0.0),
           (D.H_LINK_R1 * math.cos(D.H_LINK_GAM),
            D.H_LINK_R1 * math.sin(D.H_LINK_GAM))]
    prof = _round_poly(tri, (0.17, 0.115, 0.115), seg=6)
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.13, sy * 0.245))
        m.extrude(prof, y0, y1)
    for px, pz in tri:
        m.cylinder((px, -0.26, pz), (px, 0.26, pz), 0.055, seg=12)
    return m


def gen_dogbone() -> Mesh:
    """dogbone 双片扁杆（两端圆头 + 销）。局部原点 = BUCKET_LUG，+x 指向 P2。

    中面 |y| 0.02…0.115，比 H-link 更靠内一层 —— 两者在同一组销上但不同
    平面，不会互相磨。P2 端套在 H-link 自己那根跨 ±0.26 的销上，所以这里
    只做 BUCKET_LUG 端的销（穿耳板和斗壳缺口）。
    """
    m = Mesh("dogbone")
    L = D.DOGBONE_LEN
    prof = rounded_rect(0.0, L, -0.075, 0.075, 0.075)
    for sy in (-1, 1):
        y0, y1 = sorted((sy * 0.02, sy * 0.115))
        m.extrude(prof, y0, y1)
    m.cylinder((0.0, -0.19, 0.0), (0.0, 0.19, 0.0), 0.055, seg=12)
    return m


def gen_bucket_teeth() -> Mesh:
    """斗齿 = 齿座（adapter）+ 尖齿（point），五齿。

    上一版的齿只有 0.21 m、根部 0.17 m 宽，正交渲染里读成刃口上几根小尖刺。
    真机是两段：齿座短而方、直接焊在刃口上，尖齿从齿座里套出去收成楔形；
    两段之间有一道台肩，光照在那儿断开，远看才认得出是斗齿而不是毛刺。
    齿尖总伸出切削刃 0.315 m（20 t 档 0.25~0.35 m）。
    """
    m = Mesh("bucket_teeth")
    a1 = BUCKET_A1
    dx, dz = math.cos(a1), math.sin(a1)          # 径向 = 齿尖方向
    px, pz = -math.sin(a1), math.cos(a1)         # 沿刃口展开方向
    rim = (BUCKET_CX + BUCKET_R_OUT * dx, BUCKET_CZ + BUCKET_R_OUT * dz)

    def P(along, side):
        """沿刃口方向 along、横向 side 的点（rim 为原点）。"""
        return (rim[0] + along * dx + side * px,
                rim[1] + along * dz + side * pz)

    for ty in BUCKET_TEETH_Y:
        # 齿座：从刃口里侧 0.12 m 一直包到刃口外 0.075 m
        m.extrude([P(-0.12, 0.085), P(-0.12, -0.085),
                   P(0.075, -0.078), P(0.075, 0.078)],
                  ty - 0.060, ty + 0.060)
        # 尖齿：楔形，从齿座里伸出去 0.315 m
        m.extrude([P(0.060, 0.072), P(0.060, -0.072),
                   P(0.200, -0.040), P(0.315, -0.012),
                   P(0.315, 0.012), P(0.200, 0.040)],
                  ty - 0.052, ty + 0.052)
    return m


def gen_cyl_barrel(length, half_width, radius) -> Mesh:
    """油缸缸筒。沿 +x 从 0 到 length；half_width>0 时左右各一根。"""
    m = Mesh("cyl_barrel")
    if half_width > 0:
        for sy in (-1, 1):
            y = sy * half_width
            m.cylinder((0.0, y, 0.0), (length, y, 0.0), radius, seg=16)
            # 缸头
            m.cylinder((-0.06, y, 0.0), (0.04, y, 0.0), radius * 1.25, seg=16)
    else:
        m.cylinder((0.0, 0.0, 0.0), (length, 0.0, 0.0), radius, seg=16)
        m.cylinder((-0.06, 0.0, 0.0), (0.04, 0.0, 0.0), radius * 1.25, seg=16)
    return m


def gen_cyl_rod(length, half_width, radius) -> Mesh:
    """活塞杆。原点在缸筒末端，沿 +x 伸出 length。"""
    m = Mesh("cyl_rod")
    if half_width > 0:
        for sy in (-1, 1):
            y = sy * half_width
            m.cylinder((0.0, y, 0.0), (length, y, 0.0), radius, seg=14)
            m.cylinder((length - 0.05, y, 0.0), (length + 0.03, y, 0.0),
                       radius * 1.35, seg=14)
    else:
        m.cylinder((0.0, 0.0, 0.0), (length, 0.0, 0.0), radius, seg=14)
        m.cylinder((length - 0.05, 0.0, 0.0), (length + 0.03, 0.0, 0.0),
                   radius * 1.35, seg=14)
    return m


# --------------------------------------------------------------------------
# 轮廓裁剪：把闭合多边形裁到 [xa, xb] 区间，用于分段改宽度的梁
# --------------------------------------------------------------------------

def _clip_profile(prof, xa, xb):
    """把闭合轮廓按 x 区间裁一刀（Sutherland–Hodgman，两条竖线夹住）。"""
    def clip(poly, keep_left, x):
        out = []
        n = len(poly)
        for k in range(n):
            p, q = poly[k], poly[(k + 1) % n]
            pin = (p[0] <= x) if keep_left else (p[0] >= x)
            qin = (q[0] <= x) if keep_left else (q[0] >= x)
            if pin:
                out.append(p)
            if pin != qin:
                t = (x - p[0]) / (q[0] - p[0])
                out.append((x, p[1] + (q[1] - p[1]) * t))
        return out

    poly = list(prof)
    poly = clip(poly, False, xa)
    if len(poly) < 3:
        return []
    poly = clip(poly, True, xb)
    # 去掉相邻重复点
    clean = []
    for p in poly:
        if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    if len(clean) > 1 and math.hypot(clean[0][0] - clean[-1][0],
                                     clean[0][1] - clean[-1][1]) < 1e-6:
        clean.pop()
    return clean if len(clean) >= 3 else []


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.normpath(os.path.join(here, "..", "urdf", "meshes"))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=default_out)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    # 油缸参数：(名字, 缸筒长, 半间距, 缸半径, 活塞杆长, 杆半径)
    # 全部取自 design.CYLINDERS —— 那是铰点、行程、半径的唯一来源，
    # urdf/excavator.urdf 和 excavator_sim/cylinders.py 也读同一张表。
    # 缸筒长 + 杆长 = Lmax，validate_kinematics.py 会拿实测行程复核。
    cyl_specs = [
        (name, c["barrel"], c["half_y"], c["r_barrel"], c["rod"], c["r_rod"])
        for name, c in D.CYLINDERS.items()
    ]

    parts = [
        ("base_frame.obj", "steel_mid", gen_base_frame()),
        ("track_belt.obj", "track_dark", gen_track_belt()),
        ("track_shoe.obj", "track_shoe", gen_track_shoe()),
        ("track_wheel.obj", "steel_mid", gen_track_wheel()),
        ("house_deck.obj", "machine_yellow", gen_house_deck()),
        ("house_engine.obj", "machine_yellow_dark", gen_house_engine()),
        ("counterweight.obj", "steel_mid", gen_counterweight()),
        ("cab_frame.obj", "machine_yellow", gen_cab_frame()),
        ("cab_glass.obj", "cab_glass", gen_cab_glass()),
        ("cab_trim.obj", "track_dark", gen_cab_trim()),
        ("handrail.obj", "steel_light", gen_handrail()),
        ("boom.obj", "machine_yellow", gen_boom()),
        ("boom_pipe.obj", "steel_light", gen_boom_pipe()),
        ("arm.obj", "machine_yellow", gen_arm()),
        ("h_link.obj", "machine_yellow_dark", gen_h_link()),
        ("dogbone.obj", "machine_yellow_dark", gen_dogbone()),
        ("bucket.obj", "bucket_steel", gen_bucket()),
        ("bucket_side.obj", "track_shoe", gen_bucket_side()),
        ("bucket_teeth.obj", "steel_light", gen_bucket_teeth()),
    ]

    total_v = total_t = 0
    written = set()
    for fname, mtl, mesh in parts:
        path = os.path.join(args.out, fname)
        mesh.save(path, mtl)
        written.add(fname)
        written.add(os.path.splitext(fname)[0] + ".mtl")
        v, t = mesh.stats()
        total_v += v
        total_t += t
        print("  %-20s %6d verts %6d tris" % (fname, v, t))

    for name, barrel_len, half_w, radius, rod_len, rod_r in cyl_specs:
        mb = gen_cyl_barrel(barrel_len, half_w, radius)
        mb.save(os.path.join(args.out, name + "_barrel.obj"), "steel_mid")
        mr = gen_cyl_rod(rod_len, half_w, rod_r)
        mr.save(os.path.join(args.out, name + "_rod.obj"), "steel_light")
        written.add(name + "_barrel.obj")
        written.add(name + "_barrel.mtl")
        written.add(name + "_rod.obj")
        written.add(name + "_rod.mtl")
        v1, t1 = mb.stats()
        v2, t2 = mr.stats()
        total_v += v1 + v2
        total_t += t1 + t2
        print("  %-20s %6d verts %6d tris  (barrel)" %
              (name + "_barrel.obj", v1, t1))
        print("  %-20s %6d verts %6d tris  (rod)" %
              (name + "_rod.obj", v2, t2))

    # 清掉上一次生成、这次已经没有对应图元的陈旧文件。删掉一个 .obj 却把
    # 它的 .mtl 留在目录里，install/share 里就会多一个没人引用的材质文件；
    # 反过来留一个旧 .obj 更糟 —— URDF 可能还指着它，构建能过、rviz 里却是
    # 上一版的形状（"静默丢失资源"的孪生问题：静默残留旧资源）。
    stale = []
    present = sorted(glob.glob(os.path.join(args.out, "*.obj")) +
                     glob.glob(os.path.join(args.out, "*.mtl")))
    for p in present:
        if os.path.basename(p) not in written:
            os.remove(p)
            stale.append(os.path.basename(p))
    if stale:
        print("  删除陈旧文件: %s" % ", ".join(stale))

    print("\n%d parts, %d verts, %d tris -> %s" %
          (len(parts) + 2 * len(cyl_specs), total_v, total_t, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
