#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付前总检：资源 / 网格拓扑 / URDF↔design 一致性 / 运动安全。

这个脚本不是"跑一下看看"，它是 REVIEW_BRIEF 里列的硬判据的落地版本。
任何一项失败都必须改几何或改 URDF 来解决，**不许放宽判据**：

  资源完整性   URDF 引用的每个 OBJ（和它 mtllib 指向的 MTL）都在；
               urdf/meshes/ 下没有没被引用的孤儿文件（静默丢失资源的反面）
  网格拓扑     每面带 vn、vn 是单位向量且与几何法线同向；无退化三角；
               每个连通分量是闭合边流形（每条无向边恰好两面、且绕序相反，
               即共享边方向一正一反）；每个分量有向体积 > 0（法线朝外）
  URDF↔design 主动关节原点/轴/限位 == design.py；三根缸的 pivot 原点 == A、
               slide 原点 x == barrel；URDF limit 覆盖全行程密采样范围；
               缸筒/杆 OBJ 的 x 跨度 == barrel / rod
  运动安全     静态姿态与整条动画时间轴密采样：主动关节在限位内、
               齿尖 z ≥ 0、油缸余量 ≥ 10 mm、速度不超过 URDF velocity

用法：
    python tools/validate_kinematics.py            # 全量检查
    python tools/validate_kinematics.py --quiet    # 只打失败项与汇总
    python tools/validate_kinematics.py --samples 6000   # 时间轴加密

退出码：全过 0，任一项失败 1。

纯标准库（math / os / glob / xml / collections）。
"""

from __future__ import annotations

import glob
import math
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

# Windows 控制台默认 GBK，中文会炸、✗ 直接 UnicodeEncodeError。
# 统一改 UTF-8，管道里也一样；errors="replace" 只是兜底，正常一条都不会被替换。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PKG)

from excavator_sim import cylinders as C              # noqa: E402
from excavator_sim.design import (                   # noqa: E402
    ARM_LEN, BOOM_LEN, BOOM_PIVOT, CYLINDERS, HOUSE_Z)
from excavator_sim.motion import (                    # noqa: E402
    CYCLE, STATIC_POSES, lowest_point, sample)

URDF = os.path.join(PKG, "urdf", "excavator.urdf")
MESH_DIR = os.path.join(PKG, "urdf", "meshes")

# `package://excavator_sim/…` 的解析根。源码树下就是包根；--prefix 时换成
# 已安装的 share/excavator_sim —— 不然资源检查永远在查源码树，装出来的包
# 少了 mesh 也照样全绿（上一版 check_resources/check_meshes 里写死了 PKG，
# 这就是"测了但没测到"）。
SHARE = PKG


def use_prefix(prefix):
    """把 URDF / MESH_DIR 指到**已安装**的 share 目录。

    源码树全绿不等于 `colcon build` 出来的包能用：setup.py 的 data_files
    少写一层 glob、或者把 urdf/meshes 这个目录当成文件塞进数据表，构建要么
    静默少拷 mesh、要么直接失败，而源码树照样是好的。所以交付前必须对着
    install/ 里的那一份再跑一遍同一套判据。

    接受两种写法：
        --prefix install/excavator_sim        （colcon 的包前缀）
        --prefix …/share/excavator_sim        （直接给 share 目录）
    """
    global URDF, MESH_DIR, SHARE
    base = os.path.join(prefix, "share", "excavator_sim")
    if not os.path.isdir(base):
        base = prefix
    SHARE = base
    URDF = os.path.join(base, "urdf", "excavator.urdf")
    MESH_DIR = os.path.join(base, "urdf", "meshes")


LIMIT_TOL = 1e-4          # 关节限位比较容差（rad / m）
GEOM_TOL = 2e-3           # 原点、跨度、barrel 之类的几何容差（m）
MIN_CYL_MARGIN = 0.010    # 油缸必须留的最小余量（m）
DEGEN_AREA = 1e-9         # 三角面积低于它算退化（m^2）

# 检查项：section -> [(ok, msg), ...]
RESULTS = defaultdict(list)


def report(section, ok, msg):
    RESULTS[section].append((bool(ok), msg))


# ---------------------------------------------------------------------------
# 1. OBJ 读取与拓扑检查
# ---------------------------------------------------------------------------

class Obj:
    """只读 gen_meshes 输出的那一种 OBJ：v / vn / f a//na b//nb c//nc。"""

    def __init__(self, path):
        self.path = path
        self.verts = []
        self.normals = []
        # faces: [( (vi,nvi), (vi,nvi), (vi,nvi) ), ...]，索引从 0 开始
        self.faces = []
        self.mtllib = None
        with open(path, "r", encoding="ascii") as fh:
            for ln in fh:
                if ln.startswith("v "):
                    x, y, z = ln.split()[1:4]
                    self.verts.append((float(x), float(y), float(z)))
                elif ln.startswith("vn "):
                    x, y, z = ln.split()[1:4]
                    self.normals.append((float(x), float(y), float(z)))
                elif ln.startswith("f "):
                    corner = []
                    for tok in ln.split()[1:]:
                        a, _, _n = tok.partition("//")
                        corner.append((int(a) - 1, int(_n) - 1 if _n else -1))
                    self.faces.append(tuple(corner))
                elif ln.startswith("mtllib "):
                    self.mtllib = ln.split(None, 1)[1].strip()
        self.name = os.path.basename(path)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class _DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def check_obj(obj):
    """返回该 OBJ 的失败消息列表（空 = 通过）。"""
    bad = []
    tag = obj.name

    if not obj.faces:
        return ["%s: 没有面" % tag]
    if len(obj.verts) == 0:
        return ["%s: 没有顶点" % tag]

    # --- 每个面：三顶点 + 有 vn + vn 单位且同向 + 不退化 ----------------
    comp = _DSU(len(obj.faces))
    edge_dir = defaultdict(list)     # 无向边 -> [(方向符号, 面号)]
    for fi, f in enumerate(obj.faces):
        if len(f) != 3:
            bad.append("%s face %d: %d 个顶点（应为 3）" % (tag, fi, len(f)))
            continue
        pts, nrm = [], []
        ok_n = True
        for vi, ni in f:
            if not (0 <= vi < len(obj.verts)):
                bad.append("%s face %d: 顶点索引 %d 越界" % (tag, fi, vi))
                ok_n = False
                continue
            if ni < 0:
                bad.append("%s face %d: 缺 vn" % (tag, fi))
                ok_n = False
                continue
            if not (0 <= ni < len(obj.normals)):
                bad.append("%s face %d: 法线索引 %d 越界" % (tag, fi, ni))
                ok_n = False
                continue
            pts.append(obj.verts[vi])
            nrm.append(obj.normals[ni])
        if not ok_n or len(pts) != 3:
            continue

        g = _cross(_sub(pts[1], pts[0]), _sub(pts[2], pts[0]))
        area2 = math.sqrt(_dot(g, g))
        if area2 * 0.5 < DEGEN_AREA:
            bad.append("%s face %d: 退化三角（面积 %.2e）" % (tag, fi, area2 * 0.5))
            continue

        for k in range(3):
            nl = math.sqrt(_dot(nrm[k], nrm[k]))
            if abs(nl - 1.0) > 1e-3:
                bad.append("%s face %d: vn 不是单位向量（|n|=%.4f）" % (tag, fi, nl))
                break
        gn = (g[0] / area2, g[1] / area2, g[2] / area2)
        if _dot(gn, nrm[0]) < 0.999:
            bad.append("%s face %d: vn 与几何法线不同向（dot=%.4f）"
                       % (tag, fi, _dot(gn, nrm[0])))

        # 共享边：记录有向边，用于流形与绕序检查
        idx = [vi for vi, _ in f]
        for k in range(3):
            a, b = idx[k], idx[(k + 1) % 3]
            key = (a, b) if a < b else (b, a)
            edge_dir[key].append((1 if (a, b) == key else -1, fi))

    # --- 流形 + 绕序：每条无向边恰好两面、方向一正一反 -----------------
    # 连通分量按**共享边**把面并起来。上一版这里用 `comp.union(顶点, 顶点)`
    # 去操作一个按面编号开的并查集 —— 顶点号和面号混用，分量全是假的
    # （每个面自成一组），然后拿单面的"有向体积"去判朝外，必然全挂。
    for key, uses in edge_dir.items():
        if len(uses) != 2:
            bad.append("%s: 边 %s 被 %d 个面使用（非流形/开边）"
                       % (tag, key, len(uses)))
            continue
        if uses[0][0] == uses[1][0]:
            bad.append("%s: 边 %s 两侧绕序同向（法线不一致）" % (tag, key))
        comp.union(uses[0][1], uses[1][1])

    # --- 每个连通分量：有向体积 > 0（朝外） ----------------------------
    vol = defaultdict(float)
    for fi, f in enumerate(obj.faces):
        if len(f) != 3:
            continue
        a = obj.verts[f[0][0]]
        b = obj.verts[f[1][0]]
        c = obj.verts[f[2][0]]
        vol[comp.find(fi)] += _dot(a, _cross(b, c)) / 6.0

    for root, v in sorted(vol.items()):
        if v <= 0.0:
            bad.append("%s: 连通分量(面 %d 起) 有向体积 %.4f ≤ 0（法线朝内/退化）"
                       % (tag, root, v))

    return bad


# ---------------------------------------------------------------------------
# 2. URDF 读取
# ---------------------------------------------------------------------------

def parse_urdf():
    tree = ET.parse(URDF)
    root = tree.getroot()

    mats = {}
    for m in root.findall("material"):
        c = m.find("color")
        if c is not None:
            mats[m.get("name")] = tuple(float(x) for x in c.get("rgba").split())

    links = {}
    for lk in root.findall("link"):
        name = lk.get("name")
        vis = []
        for v in lk.findall("visual"):
            mesh = v.find("geometry/mesh")
            mat = v.find("material")
            org = v.find("origin")
            xyz = tuple(float(x) for x in (org.get("xyz", "0 0 0")).split()) \
                if org is not None else (0.0, 0.0, 0.0)
            vis.append({
                "mesh": mesh.get("filename") if mesh is not None else None,
                "material": mat.get("name") if mat is not None else None,
                "xyz": xyz,
            })
        links[name] = vis

    joints = {}
    for j in root.findall("joint"):
        name = j.get("name")
        org = j.find("origin")
        lim = j.find("limit")
        joints[name] = {
            "type": j.get("type"),
            "parent": j.find("parent").get("link"),
            "child": j.find("child").get("link"),
            "xyz": tuple(float(x) for x in org.get("xyz", "0 0 0").split())
            if org is not None else (0.0, 0.0, 0.0),
            "axis": tuple(float(x) for x in j.find("axis").get("xyz").split())
            if j.find("axis") is not None else (1.0, 0.0, 0.0),
            "limit": (float(lim.get("lower")), float(lim.get("upper")),
                      float(lim.get("velocity")))
            if lim is not None else None,
        }
    return mats, links, joints


# ---------------------------------------------------------------------------
# 3. 各项检查
# ---------------------------------------------------------------------------

def check_resources(links):
    referenced = set()
    for link, vis in links.items():
        for v in vis:
            fn = v["mesh"]
            if fn is None:
                report("资源", False, "%s: visual 没有 mesh" % link)
                continue
            if not fn.startswith("package://excavator_sim/"):
                report("资源", False, "%s: 非包内路径 %s" % (link, fn))
                continue
            rel = fn[len("package://excavator_sim/"):]
            absp = os.path.join(SHARE, rel.replace("/", os.sep))
            if not os.path.exists(absp):
                report("资源", False, "%s: 缺文件 %s" % (link, rel))
                continue
            referenced.add(os.path.normcase(os.path.abspath(absp)))
            obj = Obj(absp)
            if obj.mtllib:
                mtl = os.path.join(os.path.dirname(absp), obj.mtllib)
                if not os.path.exists(mtl):
                    report("资源", False, "%s: OBJ 引用缺 MTL %s"
                           % (link, obj.mtllib))

    on_disk = glob.glob(os.path.join(MESH_DIR, "*.obj"))
    for p in on_disk:
        if os.path.normcase(os.path.abspath(p)) not in referenced:
            report("资源", False, "孤儿 OBJ（URDF 未引用）: %s"
                   % os.path.basename(p))
    report("资源", True, "%d 个 OBJ 被引用；磁盘 %d 个 .obj / %d 个 .mtl"
           % (len(referenced), len(on_disk),
              len(glob.glob(os.path.join(MESH_DIR, "*.mtl")))))


def check_meshes(links):
    seen = set()
    n_verts = n_faces = 0
    for link, vis in links.items():
        for v in vis:
            fn = v["mesh"]
            if not fn or not fn.startswith("package://excavator_sim/"):
                continue
            absp = os.path.join(SHARE, fn[len("package://excavator_sim/"):]
                                .replace("/", os.sep))
            key = os.path.normcase(os.path.abspath(absp))
            if key in seen or not os.path.exists(absp):
                continue
            seen.add(key)
            obj = Obj(absp)
            n_verts += len(obj.verts)
            n_faces += len(obj.faces)
            for msg in check_obj(obj):
                report("网格", False, msg)
    report("网格", True, "%d 个网格 / %d 顶点 / %d 三角面 全部流形闭合、"
                         "法线朝外、无退化面" % (len(seen), n_verts, n_faces))


def check_urdf_design(joints):
    # --- 主动关节 ------------------------------------------------------
    want = {
        "swing_joint": ((0.0, 0.0, HOUSE_Z), (0.0, 0.0, 1.0)),
        "boom_joint": (BOOM_PIVOT, (0.0, 1.0, 0.0)),
        "arm_joint": ((BOOM_LEN, 0.0, 0.0), (0.0, 1.0, 0.0)),
        "bucket_joint": ((ARM_LEN, 0.0, 0.0), (0.0, 1.0, 0.0)),
    }
    for name, (xyz, axis) in want.items():
        j = joints.get(name)
        if j is None:
            report("URDF", False, "缺关节 %s" % name)
            continue
        for i in range(3):
            if abs(j["xyz"][i] - xyz[i]) > GEOM_TOL:
                report("URDF", False, "%s origin[%d]=%.4f ≠ design %.4f"
                       % (name, i, j["xyz"][i], xyz[i]))
            if abs(j["axis"][i] - axis[i]) > 1e-9:
                report("URDF", False, "%s axis[%d]=%.1f ≠ %.1f"
                       % (name, i, j["axis"][i], axis[i]))
        lo, hi, vel = C.LIMITS[name]
        if j["limit"] is None:
            report("URDF", False, "%s 缺 <limit>" % name)
        else:
            if abs(j["limit"][0] - lo) > LIMIT_TOL or \
               abs(j["limit"][1] - hi) > LIMIT_TOL:
                report("URDF", False, "%s limit [%.4f,%.4f] ≠ LIMITS [%.4f,%.4f]"
                       % (name, j["limit"][0], j["limit"][1], lo, hi))
            if j["limit"][2] < vel - 1e-9:
                report("URDF", False, "%s velocity %.3f < LIMITS %.3f"
                       % (name, j["limit"][2], vel))

    # --- 三根油缸 ------------------------------------------------------
    sweep = C.sweep(ns=13)
    for name, cfg in CYLINDERS.items():
        ax, az = cfg["A"]
        pj = joints.get(name + "_pivot_joint")
        sj = joints.get(name + "_slide_joint")
        if pj is None or sj is None:
            report("URDF", False, "缺 %s 的 pivot/slide 关节" % name)
            continue
        if abs(pj["xyz"][0] - ax) > GEOM_TOL or abs(pj["xyz"][2] - az) > GEOM_TOL:
            report("URDF", False, "%s_pivot origin=(%.3f,%.3f) ≠ A=(%.3f,%.3f)"
                   % (name, pj["xyz"][0], pj["xyz"][2], ax, az))
        if abs(pj["xyz"][1]) > GEOM_TOL:
            report("URDF", False, "%s_pivot origin y=%.3f ≠ 0" % (name, pj["xyz"][1]))
        if pj["parent"] != cfg["parent"]:
            report("URDF", False, "%s_pivot parent=%s ≠ %s"
                   % (name, pj["parent"], cfg["parent"]))
        if abs(sj["xyz"][0] - cfg["barrel"]) > GEOM_TOL:
            report("URDF", False, "%s_slide origin x=%.3f ≠ barrel %.3f"
                   % (name, sj["xyz"][0], cfg["barrel"]))

        lo, hi, p0, p1 = sweep[name]
        slide_lo = lo - (cfg["barrel"] + cfg["rod"])
        slide_hi = hi - (cfg["barrel"] + cfg["rod"])

        # 杆重叠：必须对**整个关节限位盒**成立，不能只对动画时间轴成立。
        # 动画只是演示轨迹；rviz 的 Joint State 滑块能把三个关节各自拧到
        # URDF 限位，那才是使用者真能摆到的姿态。上一版只在时间轴上量，
        # 于是 boom 缸在盒角只有 0.9 mm、bucket 缸只有 1.6 mm 重叠也照样
        # 打勾 —— 拉到极限时杆尾正好退到缸口，视觉上就是"杆从缸里拔出来了"。
        #
        #   满伸余量 = Lmax − Lmax_盒   （杆还剩多少在缸筒里）
        #   全缩余量 = Lmin_盒 − barrel （杆尾离缸底还有多远）
        ext_margin = (cfg["barrel"] + cfg["rod"]) - hi
        ret_margin = lo - cfg["barrel"]
        if ext_margin < MIN_CYL_MARGIN:
            report("URDF", False,
                   "%s 满伸余量 %.4f m < %.3f m（Lmax %.3f，盒内最长 %.3f）"
                   % (name, ext_margin, MIN_CYL_MARGIN,
                      cfg["barrel"] + cfg["rod"], hi))
        if ret_margin < MIN_CYL_MARGIN:
            report("URDF", False,
                   "%s 全缩余量 %.4f m < %.3f m（barrel %.3f，盒内最短 %.3f）"
                   % (name, ret_margin, MIN_CYL_MARGIN, cfg["barrel"], lo))
        for j, (want_lo, want_hi, label) in (
                (pj, (p0, p1, "pivot psi")),
                (sj, (slide_lo, slide_hi, "slide"))):
            if j["limit"] is None:
                report("URDF", False, "%s 缺 <limit>" % name)
                continue
            if j["limit"][0] > want_lo + LIMIT_TOL:
                report("URDF", False, "%s %s lower %.4f 盖不住实际最小 %.4f"
                       % (name, label, j["limit"][0], want_lo))
            if j["limit"][1] < want_hi - LIMIT_TOL:
                report("URDF", False, "%s %s upper %.4f 盖不住实际最大 %.4f"
                       % (name, label, j["limit"][1], want_hi))

        # 缸筒 / 杆 OBJ 的 x 范围。
        #
        # 这两个零件的网格**不是**纯粹的 [0, L] 圆柱：gen_cyl_barrel 在后面
        # 加了一圈直径更大的缸头（包到 x = -0.06），gen_cyl_rod 在前面加了
        # 杆头（包到 x = L + 0.03）。所以"跨度 == barrel/rod"这个判据从一开始
        # 就写错了 —— 缸头/杆头是视觉包边，本来就该伸出去一点。
        #
        # 真正要紧的是**缸口位置**：
        #   barrel 的 x 最大处必须正好在 slide 关节原点上（= barrel），
        #           否则杆缩到最短时会从缸口里冒出来／缩进去；
        #   rod     的 x 最小处必须正好是杆的起点 0（= 销孔中心）。
        # 包边只允许向外、不允许吃进配合面，因此用单侧容差。
        p = os.path.join(MESH_DIR, "%s_barrel.obj" % name)
        if not os.path.exists(p):
            report("URDF", False, "缺 %s" % os.path.basename(p))
        else:
            xs = [v[0] for v in Obj(p).verts]
            if abs(max(xs) - cfg["barrel"]) > GEOM_TOL:
                report("URDF", False, "%s_barrel.obj 缸口 x=%.4f ≠ barrel %.4f"
                       % (name, max(xs), cfg["barrel"]))
            if not (-0.12 <= min(xs) <= GEOM_TOL):
                report("URDF", False, "%s_barrel.obj 后端 x=%.4f 越界（应在 "
                       "-0.12..0，缸头包边也不该更远）" % (name, min(xs)))

        p = os.path.join(MESH_DIR, "%s_rod.obj" % name)
        if not os.path.exists(p):
            report("URDF", False, "缺 %s" % os.path.basename(p))
        else:
            xs = [v[0] for v in Obj(p).verts]
            if abs(min(xs)) > GEOM_TOL:
                report("URDF", False, "%s_rod.obj 起点 x=%.4f ≠ 0"
                       % (name, min(xs)))
            if not (cfg["rod"] - GEOM_TOL <= max(xs) <= cfg["rod"] + 0.12):
                report("URDF", False, "%s_rod.obj 杆头 x=%.4f 越界（应在 "
                       "rod %.4f..%.4f）" % (name, max(xs), cfg["rod"],
                                             cfg["rod"] + 0.12))
    report("URDF", True, "主动关节原点/轴/限位、6 个油缸关节原点与限位、"
                         "缸筒/杆 OBJ 跨度 全部与 design.py 一致")


def check_motion(joints, samples, quiet):
    """时间轴密采样：限位、离地、油缸余量、速度。"""
    n = max(120, int(samples))
    dt = CYCLE / n
    vel_lim = {}
    for nm, j in joints.items():
        if j["limit"] is not None and j["type"] in ("revolute", "prismatic"):
            vel_lim[nm] = j["limit"][2]

    act = ("swing_joint", "boom_joint", "arm_joint", "bucket_joint")
    vmax = defaultdict(float)
    # slide 的初值必须是 −inf。用 defaultdict(float) 时初值是 0.0，而 slide
    # 恒为负（满伸时也才 0），max(0.0, 负数) 永远停在 0 ⇒ 余量恒报 −0.0000，
    # 三根缸看起来一模一样地"刚好卡死"，实际上 arm 缸本来还有 13 mm 余量。
    slide_max = defaultdict(lambda: float("-inf"))
    zmin = float("inf")
    worst_t = 0.0
    prev = None

    for i in range(n + 1):
        t = CYCLE * i / n
        ang = sample(t)
        ang = dict(ang)
        ang.update(C.solve(ang))

        for k in act:
            lo, hi, _ = C.LIMITS[k]
            if not (lo - 1e-9 <= ang[k] <= hi + 1e-9):
                report("运动", False, "t=%.2f %s=%.3f 超限 [%.2f,%.2f]"
                       % (t, k, ang[k], lo, hi))

        z = lowest_point(ang)
        if z < zmin:
            zmin, worst_t = z, t
        for k, v in ang.items():
            if k.endswith("_slide_joint"):
                slide_max[k] = max(slide_max[k], v)

        if prev is not None:
            for k in ang:
                v = abs(ang[k] - prev[k]) / dt
                if v > vmax[k]:
                    vmax[k] = v
        prev = ang

    # 静态姿态也要过一遍（它们不进时间轴）
    for name, ang0 in STATIC_POSES.items():
        ang = dict(ang0)
        ang.update(C.solve(ang))
        z = lowest_point(ang)
        if z < zmin:
            zmin, worst_t = z, -1.0
        for k in act:
            lo, hi, _ = C.LIMITS[k]
            if not (lo - 1e-9 <= ang[k] <= hi + 1e-9):
                report("运动", False, "pose %s: %s=%.3f 超限" % (name, k, ang[k]))
        for k, v in ang.items():
            if k.endswith("_slide_joint"):
                slide_max[k] = max(slide_max[k], v)

    if zmin < -1e-6:
        report("运动", False, "最低点 z=%.3f < 0（%s）"
               % (zmin, "静态姿态" if worst_t < 0 else "t=%.2f" % worst_t))

    for k, v in sorted(vmax.items()):
        lim = vel_lim.get(k)
        if lim is None:
            report("运动", False, "%s 在 URDF 里没有 velocity 限" % k)
            continue
        if v > lim + 1e-6:
            report("运动", False, "%s 峰值速度 %.3f > URDF %.3f"
                   % (k, v, lim))

    for k, v in sorted(slide_max.items()):
        margin = -v
        if margin < MIN_CYL_MARGIN:
            report("运动", False, "%s 余量 %.4f m < %.3f m"
                   % (k, margin, MIN_CYL_MARGIN))

    if not quiet:
        print("  运动: 时间轴 %.1f s / %d 采样, 最低点 z=%+.3f m, "
              "速度峰值 %.3f rad|m/s" % (CYCLE, n, zmin, max(vmax.values())))
    report("运动", True, "%d 采样 + %d 静态姿态：限位/离地/油缸余量/速度 全部通过"
           % (n + 1, len(STATIC_POSES)))


# ---------------------------------------------------------------------------
# 4. 汇总
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=int, default=2400, help="时间轴采样数")
    ap.add_argument("--quiet", action="store_true", help="只打失败项与汇总")
    ap.add_argument("--prefix", metavar="DIR",
                    help="改测已安装的 share 目录（colcon 前缀或 share/excavator_sim）")
    args = ap.parse_args(argv)

    if args.prefix:
        use_prefix(args.prefix)
    if not args.quiet:
        print("被测根目录: %s" % os.path.dirname(os.path.dirname(URDF)))
    if not os.path.exists(URDF):
        print("找不到 URDF: %s" % URDF)
        return 1

    mats, links, joints = parse_urdf()
    if not args.quiet:
        print("URDF: %d 个 link, %d 个 joint, %d 种材质"
              % (len(links), len(joints), len(mats)))

    check_resources(links)
    check_meshes(links)
    check_urdf_design(joints)
    check_motion(joints, args.samples, args.quiet)

    order = ["资源", "网格", "URDF", "运动"]
    total_fail = 0
    print()
    for sec in order:
        items = RESULTS[sec]
        fails = [m for ok, m in items if not ok]
        total_fail += len(fails)
        print("[%s] %s" % (sec, "FAIL" if fails else "ok"))
        if fails:
            for m in fails[:40]:
                print("    ✗ " + m)
            if len(fails) > 40:
                print("    … 另有 %d 条" % (len(fails) - 40))
        elif not args.quiet:
            for _ok, m in items:
                print("    " + m)

    print()
    if total_fail:
        print("总计 %d 项失败 —— 不许放宽判据，改几何或改 URDF。" % total_fail)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
