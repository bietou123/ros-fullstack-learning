#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线预览渲染：读 URDF + OBJ 网格，在 PC 上软件光栅化出图。

用途是给造型做快速迭代 —— 平板只有一个 10 W 的 USB 口，rviz 满载时净放电，
每改一版都上板看太亏。这个脚本把 URDF 的 FK 算出来，正交投影 + z-buffer
光栅化，输出 PNG，几秒钟一张。

    python3 preview_render.py                 # 出 build/preview/*.png
    python3 preview_render.py --out D:/tmp/pv

依赖 numpy + Pillow（只在开发机上用，不影响平板运行）。
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from excavator_sim.cylinders import solve as solve_cylinders  # noqa: E402
from excavator_sim.motion import CYCLE, STATIC_POSES, sample as sample_motion  # noqa: E402

# --------------------------------------------------------------------------
# URDF 解析
# --------------------------------------------------------------------------


def rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=float)
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=float)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=float)
    return rz @ ry @ rx


def axis_angle(axis, angle: float) -> np.ndarray:
    a = np.asarray(axis, dtype=float)
    n = np.linalg.norm(a)
    if n < 1e-12 or abs(angle) < 1e-12:
        return np.eye(3)
    a = a / n
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * (k @ k)


class Urdf:
    def __init__(self, path: str):
        root = ET.parse(path).getroot()
        self.path = path
        self.urdf_dir = os.path.dirname(os.path.abspath(path))
        # URDF 在 <pkg>/urdf/ 下，package://<pkg>/a/b 要解析到 <pkg>/a/b
        self.pkg_dir = os.path.dirname(self.urdf_dir)

        self.materials = {}
        for m in root.findall("material"):
            c = m.find("color")
            if c is not None:
                rgba = [float(v) for v in c.get("rgba").split()]
                self.materials[m.get("name")] = np.array(rgba[:3]) * 255.0

        self.visuals = {}          # link -> [(mesh_abs, xyz, rpy, rgb)]
        for link in root.findall("link"):
            items = []
            for vis in link.findall("visual"):
                geo = vis.find("geometry")
                mesh = geo.find("mesh") if geo is not None else None
                if mesh is None:
                    continue
                fn = mesh.get("filename")
                if fn.startswith("file://"):
                    fn = fn[7:]
                elif fn.startswith("package://"):
                    # package://excavator_sim/urdf/meshes/x.obj
                    rel = fn.split("/", 3)[3]
                    fn = os.path.join(self.pkg_dir, *rel.split("/"))
                elif not os.path.isabs(fn):
                    fn = os.path.join(self.urdf_dir, fn)
                org = vis.find("origin")
                xyz = np.array([float(t) for t in
                                (org.get("xyz") if org is not None else "0 0 0").split()])
                rpy = [float(t) for t in
                       (org.get("rpy") if org is not None else "0 0 0").split()]
                mat = vis.find("material")
                rgb = np.array([200.0, 170.0, 40.0])
                if mat is not None and mat.get("name") in self.materials:
                    rgb = self.materials[mat.get("name")]
                items.append((fn, xyz, rpy, rgb))
            self.visuals[link.get("name")] = items

        self.joints = {}
        self.parent_of = {}
        for j in root.findall("joint"):
            parent = j.find("parent").get("link")
            child = j.find("child").get("link")
            org = j.find("origin")
            xyz = np.array([float(t) for t in
                            (org.get("xyz") if org is not None else "0 0 0").split()])
            rpy = [float(t) for t in
                   (org.get("rpy") if org is not None else "0 0 0").split()]
            ax = j.find("axis")
            axis = np.array([float(t) for t in
                             (ax.get("xyz") if ax is not None else "1 0 0").split()])
            self.joints[j.get("name")] = {
                "type": j.get("type"), "parent": parent, "child": child,
                "xyz": xyz, "rpy": rpy, "axis": axis,
            }
            self.parent_of[child] = j.get("name")

    def forward_kinematics(self, angles: dict) -> dict:
        """返回 link -> (R, t)。"""
        pose = {}
        pending = [l for l in self.visuals if l not in self.parent_of]
        for root_link in pending:
            pose[root_link] = (np.eye(3), np.zeros(3))

        changed = True
        while changed:
            changed = False
            for name, j in self.joints.items():
                if j["parent"] in pose and j["child"] not in pose:
                    pr, pt = pose[j["parent"]]
                    q = angles.get(name, 0.0)
                    if j["type"] in ("revolute", "continuous"):
                        rel_r = axis_angle(j["axis"], q)
                        rel_t = np.zeros(3)
                    elif j["type"] == "prismatic":
                        rel_r = np.eye(3)
                        a = j["axis"] / max(np.linalg.norm(j["axis"]), 1e-12)
                        rel_t = a * q
                    else:
                        rel_r = np.eye(3)
                        rel_t = np.zeros(3)
                    o_r = rpy_matrix(*j["rpy"])
                    o_t = j["xyz"]
                    pose[j["child"]] = (pr @ o_r @ rel_r, pt + pr @ (o_t + rel_r.T @ rel_t))
                    changed = True
        return pose


# --------------------------------------------------------------------------
# OBJ + 场景装配
# --------------------------------------------------------------------------

_OBJ_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def load_obj(path: str):
    if path in _OBJ_CACHE:
        return _OBJ_CACHE[path]
    verts, faces = [], []
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    idx.append(int(tok.split("/")[0]) - 1)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    v = np.array(verts, dtype=float)
    f = np.array(faces, dtype=np.int32)
    _OBJ_CACHE[path] = (v, f)
    return v, f


def build_scene(urdf: Urdf, angles: dict):
    """返回 (tris[N,3,3], colors[N,3]) 世界坐标。"""
    pose = urdf.forward_kinematics(angles)
    all_tris, all_cols = [], []
    for link, items in urdf.visuals.items():
        if link not in pose:
            continue
        lr, lt = pose[link]
        for fn, xyz, rpy, rgb in items:
            if not os.path.exists(fn):
                continue
            v, f = load_obj(fn)
            local = v @ rpy_matrix(*rpy).T + xyz
            world = local @ lr.T + lt
            all_tris.append(world[f])
            all_cols.append(np.tile(rgb, (len(f), 1)))
    if not all_tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    return np.concatenate(all_tris), np.concatenate(all_cols)


# --------------------------------------------------------------------------
# 光栅化
# --------------------------------------------------------------------------

def make_camera(yaw_deg, pitch_deg, target):
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    to_cam = np.array([math.cos(yaw) * math.cos(pitch),
                       math.sin(yaw) * math.cos(pitch),
                       math.sin(pitch)])
    fwd = -to_cam
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, world_up)
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    return fwd, right, up, np.asarray(target, dtype=float)


def fit_camera(tris_list, yaw_deg, pitch_deg, size, margin=0.93):
    """按给定视角把所有姿态的机器包围盒装进画面，返回 (cam, scale)。

    手调 target/scale 每次改造型都要重来一遍，索性按实际顶点算。
    """
    W, H = size
    fwd, right, up, _t = make_camera(yaw_deg, pitch_deg, np.zeros(3))
    pts = np.concatenate([t.reshape(-1, 3) for t in tris_list if len(t)])
    x, y = pts @ right, pts @ up
    x0, x1, y0, y1 = x.min(), x.max(), y.min(), y.max()
    scale = min(W * margin / max(x1 - x0, 1e-3),
                H * margin / max(y1 - y0, 1e-3))
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    return (fwd, right, up, right * cx + up * cy), scale


def ground_mesh(extent=11.0):
    """一块地面。有它才能一眼看出铲斗是不是穿地。"""
    q = [(-extent, -extent, 0.0), (extent, -extent, 0.0),
         (extent, extent, 0.0), (-extent, extent, 0.0)]
    tris = np.array([(q[0], q[1], q[2]), (q[0], q[2], q[3])], dtype=float)
    return tris, np.tile(np.array([58.0, 70.0, 86.0]), (2, 1))


def render(tris, cols, cam, size, scale, bg=(46, 58, 74), light=None):
    W, H = size
    fwd, right, up, target = cam
    if light is None:
        # 主光跟着机位走：从相机左上、略高打下来。固定世界方向的光会让
        # 侧视图里朝向相机的那一面整个背光，黄色全变橄榄色。
        light = -1.0 * fwd + 0.85 * up - 0.45 * right
        light = light / np.linalg.norm(light)

    img = np.zeros((H, W, 3), dtype=np.float32)
    img[:, :] = np.array(bg, dtype=np.float32)
    zbuf = np.full((H, W), 1e9, dtype=np.float32)

    if len(tris) == 0:
        return img.astype(np.uint8)

    # 顶点 → 相机坐标
    rel = tris - target
    px = rel @ right * scale + W * 0.5
    py = H * 0.5 - rel @ up * scale
    pz = rel @ fwd

    # 面法线（世界）
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    nl = np.linalg.norm(n, axis=1)
    ok = nl > 1e-9
    n = n / np.where(ok, nl, 1.0)[:, None]

    facing = n @ fwd           # <0 表示朝向相机
    shade = 0.34 + 0.72 * np.clip(n @ light, 0.0, None)
    # 一点点环境遮蔽感的竖向渐变
    vy = np.clip((tris[:, :, 2].mean(axis=1) + 0.2) / 4.0, 0.0, 1.0)
    shade = shade * (0.80 + 0.20 * vy)

    order = np.argsort(-pz.mean(axis=1))   # 远的先画，配合 z-buffer 双保险
    for i in order:
        if not ok[i] or facing[i] > -1e-6:
            continue
        x0 = max(int(np.floor(px[i].min())), 0)
        x1 = min(int(np.ceil(px[i].max())) + 1, W)
        y0 = max(int(np.floor(py[i].min())), 0)
        y1 = min(int(np.ceil(py[i].max())) + 1, H)
        if x0 >= x1 or y0 >= y1:
            continue
        ax, ay = px[i, 0], py[i, 0]
        bx, by = px[i, 1], py[i, 1]
        cx, cy = px[i, 2], py[i, 2]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        ys, xs = np.mgrid[y0:y1, x0:x1]
        xs = xs + 0.5
        ys = ys + 0.5
        w0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        w1 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * pz[i, 0] + w1 * pz[i, 1] + w2 * pz[i, 2]
        sub_z = zbuf[y0:y1, x0:x1]
        hit = inside & (z < sub_z)
        if not hit.any():
            continue
        sub_z[hit] = z[hit]
        color = np.clip(cols[i] * shade[i], 0, 255)
        img[y0:y1, x0:x1][hit] = color
    return np.clip(img, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# 出图
# --------------------------------------------------------------------------

# 姿态只写 4 个主动关节，6 个油缸关节由 cylinders.solve() 推出来 —— 与 rviz 里
# 跑的 anim_node 走同一套几何。**姿态表本体在 excavator_sim/motion.py**，
# 这里不再另存一份：以前预览叫 01_work 摆一个抬头姿态、rviz 里又摆另一个，
# 结果预览图"没有穿地"，上板一看铲斗埋进地里。
POSES = list(STATIC_POSES.items())


def with_cylinders(main_angles: dict) -> dict:
    a = dict(main_angles)
    a.setdefault("swing_joint", 0.0)
    a.update(solve_cylinders(a))
    return a

VIEWS = [
    ("side", 270.0, 3.0),   # 纯侧视（车头朝右），看剪影与工作装置轮廓
    ("q34", 315.0, 18.0),   # 前右 3/4，看箱型梁宽度、驾驶室斜面、配重后缘
    # 俯视：yaw=270 让车头朝屏幕右、机器左侧（+y）朝屏幕上方。整机在俯视下
    # 是 10×3.4 m 的长条，只有让长边落在横向才不会两边大片空白。
    # pitch 用 89° 而不是 90°，避免 fwd 与 world_up 平行导致 right 退化。
    ("top", 270.0, 89.0),
]


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    pkg = os.path.dirname(here)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--urdf", default=os.path.join(pkg, "urdf", "excavator.urdf"))
    ap.add_argument("--out", default=os.path.join(pkg, "build", "preview"))
    ap.add_argument("--width", type=int, default=760)
    ap.add_argument("--height", type=int, default=520)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    urdf = Urdf(args.urdf)
    print("links with mesh:", len([k for k, v in urdf.visuals.items() if v]))
    missing = [fn for items in urdf.visuals.values()
               for (fn, _x, _r, _c) in items if not os.path.exists(fn)]
    if missing:
        print("MISSING MESH:", missing[:4])

    gtris, gcols = ground_mesh()
    scenes = {}
    for name, angles in POSES:
        tris, cols = build_scene(urdf, with_cylinders(angles))
        scenes[name] = (np.concatenate([gtris, tris]), np.concatenate([gcols, cols]))

    tiles = {}
    for vname, yaw, pitch in VIEWS:
        cam, scale = fit_camera([scenes[n][0][2:] for n, _a in POSES],
                                yaw, pitch, (args.width, args.height))
        for name, _angles in POSES:
            tris, cols = scenes[name]
            img = render(tris, cols, cam, (args.width, args.height), scale)
            tiles[(name, vname)] = img
            out = os.path.join(args.out, "%s_%s.png" % (name, vname))
            Image.fromarray(img).save(out)
            print("  wrote", out)

    # 拼一张总览：每行一个视角，每列一个姿态
    cw, ch = args.width, args.height
    sheet = Image.new("RGB", (cw * len(POSES), ch * len(VIEWS)), (32, 40, 52))
    for r, (vname, _y, _p) in enumerate(VIEWS):
        for c, (name, _a) in enumerate(POSES):
            sheet.paste(Image.fromarray(tiles[(name, vname)]), (c * cw, r * ch))
    draw = ImageDraw.Draw(sheet)
    for c, (name, _a) in enumerate(POSES):
        draw.text((c * cw + 10, 8), name, fill=(210, 220, 235))
    for r, (vname, _y, _p) in enumerate(VIEWS):
        draw.text((8, r * ch + 8), vname, fill=(210, 220, 235))
    sheet_path = os.path.join(args.out, "sheet.png")
    sheet.save(sheet_path)
    print("  sheet ->", sheet_path)

    total_v = total_t = 0
    for items in urdf.visuals.values():
        for fn, _x, _r, _c in items:
            if os.path.exists(fn):
                v, f = load_obj(fn)
                total_v += v.shape[0]
                total_t += f.shape[0]
    print("scene: %d verts, %d tris" % (total_v, total_t))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
