"""油缸几何求解：给主关节角，算三组油缸的铰接角度与活塞杆行程。

挖机上的三根油缸都不是"直接驱动机臂"的，而是两点之间的直线执行器：
缸筒铰在上一级构件上，活塞杆顶在下一级构件的耳板上。三角关系决定了
油缸的姿态完全由主关节角唯一确定 —— 所以这里不引入新自由度，
只是把主关节角翻译成 rviz 需要的 6 个被动关节值。

    boom_cyl    A(上车平台鼻锥)  → B(动臂下缘外侧耳板)
    arm_cyl     A(动臂上缘立耳板) → B(斗杆根部上表面耳板)
    bucket_cyl  A(斗杆上表面耳板) → B(斗背顶面耳板)

URDF 里每根缸拆成两个关节：
    <name>_pivot_joint   revolute 绕 y，原点 = A，角度 ψ
    <name>_slide_joint   prismatic 沿 x，原点在缸筒末端，位移 = L - Lmax

slide 的 origin 取缸筒长度 BARREL（活塞杆完全缩回时杆座的位置），
轴 x 正向朝杆端。杆 mesh 从自身原点沿 +x 延伸 ROD 长度，
所以杆端到 A 的距离 = BARREL + slide + ROD。
令 BARREL + ROD = Lmax（杆完全伸出时）⇒ 恒有 L = Lmax + slide ≤ Lmax。

**铰点与行程的唯一来源是 excavator_sim.design.CYLINDERS**，这里不再另存一份。
（上一版三处各存一份数，design 改了这里没改，rviz 里缸筒和杆错开 0.2 m。）

纯标准库，只在 URDF 常量上做二维几何，anim_node 和平板上的任何工具都能
import，不依赖 numpy。
"""

from __future__ import annotations

import math

from .design import ARM_LEN, BOOM_LEN, BOOM_PIVOT, CYLINDERS

# ---------------------------------------------------------------------------
# 关节角下限 / 上限（必须与 excavator.urdf 的 <limit> 完全一致）
# ---------------------------------------------------------------------------
# 这些是"机器能到哪"的物理限位，不是"测试能不能过"的旋钮。改小可以让
# 行程算得好看一点，但那样 rviz 里就会看到杆顶穿缸筒 —— 所以改限位必须
# 重跑 `python -m excavator_sim.cylinders` 复核三根缸的可行域。
LIMITS = {
    "swing_joint": (-3.1416, 3.1416, 1.2),
    "boom_joint": (-1.15, 0.36, 0.7),
    "arm_joint": (-0.35, 2.60, 1.2),
    # 斗齿扫过地面的位置在 −1.10 附近；原来是 −1.90，俯身时齿尖插进地里
    "bucket_joint": (-1.10, 1.20, 1.8),
}


def _rot(x, z, th):
    """绕 y 轴转 th：x' = x cos + z sin, z' = -x sin + z cos（与 URDF Ry 一致）。"""
    c, s = math.cos(th), math.sin(th)
    return (x * c + z * s, -x * s + z * c)


def _chain(angles, cfg):
    """把 B 点从子构件系变换到 A 点所在的父构件系，返回 A→B 的 (dx, dz)。"""
    parent = cfg["parent"]
    ax, az = cfg["A"]
    bx, bz = cfg["B"]

    if parent == "house_link":
        # B 在 boom_link 系：先绕 y 转到上车系，再平移到动臂铰点
        th = angles["boom_joint"]
        rx, rz = _rot(bx, bz, th)
        return (BOOM_PIVOT[0] + rx - ax, BOOM_PIVOT[2] + rz - az)

    if parent == "boom_link":
        # 全部在 boom_link 系里比：arm_link 原点就在 (BOOM_LEN, 0)，
        # 姿态只差 arm 角本身（boom 角是这个系自己的事，不能重复乘）。
        rx, rz = _rot(bx, bz, angles["arm_joint"])
        return (BOOM_LEN + rx - ax, rz - az)

    if parent == "arm_link":
        # 全部在 arm_link 系里比：bucket_link 原点在 (ARM_LEN, 0)，只差 bucket 角。
        rx, rz = _rot(bx, bz, angles["bucket_joint"])
        return (ARM_LEN + rx - ax, rz - az)

    raise ValueError("unknown parent %r" % parent)


def solve(angles):
    """返回 {joint_name: value}，只含 6 个油缸关节。

    angles 需要含 swing_joint / boom_joint / arm_joint / bucket_joint
    （swing 不影响缸，仅用于完整性）。
    """
    out = {}
    for name, cfg in CYLINDERS.items():
        dx, dz = _chain(angles, cfg)
        length = math.hypot(dx, dz)
        # 缸筒坐标系：+x 从 A 指向 B。绕 y 转 psi 后 A→B 方向为 (cos, -sin)
        psi = math.atan2(-dz, dx)
        lmax = cfg["barrel"] + cfg["rod"]
        out[name + "_pivot_joint"] = psi
        out[name + "_slide_joint"] = length - lmax
    return out


def lengths(angles):
    """调试用：{cyl: L}。"""
    res = {}
    for name, cfg in CYLINDERS.items():
        dx, dz = _chain(angles, cfg)
        res[name] = math.hypot(dx, dz)
    return res


def sweep(ns=9):
    """按 LIMITS 密采样主关节，返回每根缸的 (Lmin, Lmax, psi_min, psi_max)。"""
    grid = {
        "boom_joint": LIMITS["boom_joint"],
        "arm_joint": LIMITS["arm_joint"],
        "bucket_joint": LIMITS["bucket_joint"],
    }
    def ramp(lo, hi):
        return [lo + (hi - lo) * i / (ns - 1) for i in range(ns)]

    out = {k: {"L": [], "psi": []} for k in CYLINDERS}
    for b in ramp(*grid["boom_joint"][:2]):
        for a in ramp(*grid["arm_joint"][:2]):
            for k in ramp(*grid["bucket_joint"][:2]):
                ang = {"swing_joint": 0.0, "boom_joint": b,
                       "arm_joint": a, "bucket_joint": k}
                ls = lengths(ang)
                sv = solve(ang)
                for name in CYLINDERS:
                    out[name]["L"].append(ls[name])
                    out[name]["psi"].append(sv[name + "_pivot_joint"])
    return {k: (min(v["L"]), max(v["L"]), min(v["psi"]), max(v["psi"]))
            for k, v in out.items()}


def check(ns=9, verbose=True):
    """复核三根缸在全关节行程内是否几何可行，返回是否全部通过。

    判据（任一不满足就是网格/URDF 里会出现穿模或缸筒见底）：
      Lmax = barrel + rod 必须 ≥ 实测最大长度（否则杆不够长）
      barrel ≥ stroke      缸筒要能容纳全部行程
      barrel ≤ Lmin        全缩时杆座不能穿出缸尾
      rod    ≤ Lmin        全缩时杆座 x ≥ 0
    """
    res = sweep(ns)
    ok = True
    rows = []
    for name, cfg in CYLINDERS.items():
        lo, hi, p0, p1 = res[name]
        lmax = cfg["barrel"] + cfg["rod"]
        stroke = hi - lo
        errs = []
        if hi > lmax + 1e-6:
            errs.append("Lmax 少了 %.3f m" % (hi - lmax))
        if cfg["barrel"] < stroke - 1e-6:
            errs.append("缸筒短于行程 %.3f m" % (stroke - cfg["barrel"]))
        if cfg["barrel"] > lo + 1e-6:
            errs.append("缸筒长于 Lmin %.3f m" % (cfg["barrel"] - lo))
        if cfg["rod"] > lo + 1e-6:
            errs.append("杆长于 Lmin %.3f m" % (cfg["rod"] - lo))
        if errs:
            ok = False
        rows.append((name, lo, hi, stroke, lmax, p0, p1,
                     lo - lmax, 0.0, "; ".join(errs)))
    if verbose:
        print("缸            Lmin    Lmax    行程   barrel+rod   psi[deg]           "
              "slide[m]          判据")
        for (name, lo, hi, stroke, lmax, p0, p1, s0, s1, err) in rows:
            print("%-12s %6.3f  %6.3f  %6.3f   %6.3f      [%+7.2f, %+7.2f]  "
                  "[%+7.3f, %+6.3f]   %s"
                  % (name, lo, hi, stroke, lmax,
                     math.degrees(p0), math.degrees(p1), s0, s1,
                     err or "OK"))
    return ok, rows


if __name__ == "__main__":
    ok, rows = check()
    print()
    # 可直接抄进 urdf/excavator.urdf 的 limit（留 0.02 rad / 0.02 m 余量）
    print("URDF limits（实测范围 + 0.02 余量）:")
    for (name, lo, hi, stroke, lmax, p0, p1, s0, s1, err) in rows:
        print('    <%s_pivot_joint> lower="%.4f" upper="%.4f"'
              % (name, p0 - 0.02, p1 + 0.02))
        print('    <%s_slide_joint> lower="%.4f" upper="%.4f"'
              % (name, s0 - 0.02, s1 + 0.02))
    print("\n%s" % ("全部可行" if ok else "有不可行项，见上表"))
    raise SystemExit(0 if ok else 1)
