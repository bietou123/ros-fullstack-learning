"""油缸几何求解：给主关节角，算三组油缸的铰接角度与活塞杆行程。

挖机上的三根油缸都不是"直接驱动机臂"的，而是两点之间的直线执行器：
缸筒铰在上一级构件上，活塞杆顶在下一级构件的耳板上。三角关系决定了
油缸的姿态完全由主关节角唯一确定 —— 所以这里不引入新自由度，
只是把主关节角翻译成 rviz 需要的被动关节值。

    boom_cyl    A(上车平台鼻锥)  → B(动臂下缘外侧耳板)
    arm_cyl     A(动臂上缘立耳板) → B(斗杆根部上表面耳板)
    bucket_cyl  A(斗杆上表面耳板) → P1(H-link 上的缸杆端销)

铲斗那一侧是**四连杆**，不是直连：

    H ──r1──→ P1   （缸杆端销，装在 H-link 三角板上）
    H ──r2──→ P2   （dogbone 端销，同板）
    P2 ──D──→ BUCKET_LUG （斗上的耳板）

H 铰在斗杆上（arm 系固定点）。给定 bucket_joint 后，BUCKET_LUG 的位置定了，
P2 是「圆心 H、半径 r2」与「圆心 lug、半径 D」两圆的交点，P1 又由 P2 绕 H
转固定角 GAM 得到 —— 整条链只剩一个自由度，可以逐帧闭式解开。
URDF 是树不能成环，所以 H-link 挂成 arm_link 的子、dogbone 挂成 bucket_link
的子，两个被动关节角全由这里算出来发布，环在运动学上是闭合的。

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

from .design import (ARM_LEN, BOOM_LEN, BOOM_PIVOT, BUCKET_LUG, CYLINDERS,
                     DOGBONE_LEN, H_LINK_GAM, H_LINK_PIN, H_LINK_R1, H_LINK_R2)

# ---------------------------------------------------------------------------
# 关节角下限 / 上限（必须与 excavator.urdf 的 <limit> 完全一致）
# ---------------------------------------------------------------------------
# 这些是"机器能到哪"的物理限位，不是"测试能不能过"的旋钮。改小可以让
# 行程算得好看一点，但那样 rviz 里就会看到杆顶穿缸筒 —— 所以改限位必须
# 重跑 `python -m excavator_sim.cylinders` 复核三根缸的可行域。
#
# h_link / dogbone 是四连杆的被动关节，没有自己的执行器：它们的上下限来自
# 4001 帧密采样（bucket_joint 全行程）实测 + 0.02 rad 余量。速度上限按
# 「bucket 限速 × 该关节最大摆速比」取，不是拍出来的。
LIMITS = {
    "swing_joint": (-3.1416, 3.1416, 1.2),
    "boom_joint": (-1.15, 0.36, 0.7),
    "arm_joint": (-0.35, 2.60, 1.2),
    # 斗齿扫过地面的位置在 −1.10 附近；原来是 −1.90，俯身时齿尖插进地里
    "bucket_joint": (-1.10, 1.20, 1.8),
    # 被动关节：范围来自 4001 帧密采样实测 + 0.02 rad 余量，速度上限 =
    # bucket 限速 1.8 × 该关节实测最大摆速比（h 1.789 → 3.22、d 0.836 → 1.51）。
    "h_link_joint": (1.8791, 4.5557, 3.4),
    "dogbone_joint": (1.3944, 2.5667, 1.6),
}


def _rot(x, z, th):
    """绕 y 轴转 th：x' = x cos + z sin, z' = -x sin + z cos（与 URDF Ry 一致）。"""
    c, s = math.cos(th), math.sin(th)
    return (x * c + z * s, -x * s + z * c)


def circle_int(c0, r0, c1, r1):
    """两圆交点，返回 (A, B) 或 None（不相交/同心）。全部在 arm 系平面内。"""
    dx, dz = c1[0] - c0[0], c1[1] - c0[1]
    d = math.hypot(dx, dz)
    if d == 0.0 or d > r0 + r1 or d < abs(r0 - r1):
        return None
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, r0 * r0 - a * a))
    mx, mz = c0[0] + a * dx / d, c0[1] + a * dz / d
    return ((mx - h * dz / d, mz + h * dx / d),
            (mx + h * dz / d, mz - h * dx / d))


def h_link_state(angles):
    """铲斗四连杆在 arm 系的状态。

    只用 bucket_joint 一个自由度。固定取 circle_int 的索引 0 分支（BR=0）：
    全行程内两叶不会交叉，取固定索引才不会在某个角度跳叶。

    返回 arm 系下的 lug / P1 / P2，以及两个被动关节角。关节角按 URDF 的
    R_y 约定取负 —— 局部 +x 轴在父系里的方向角是 −θ。
    """
    tk = angles["bucket_joint"]
    # lug 从 bucket 系转到 arm 系：bucket→arm 就是绕 y 转 +tk 再平移到斗销
    ux, uz = _rot(BUCKET_LUG[0], BUCKET_LUG[1], tk)
    lug = (ARM_LEN + ux, uz)

    pts = circle_int(H_LINK_PIN, H_LINK_R2, lug, DOGBONE_LEN)
    if pts is None:
        raise ValueError("四连杆无解：bucket_joint=%.4f 时 P2 两圆不相交" % tk)
    P2 = pts[0]

    # H-link 板是刚性三角形：P1 相对 P2 绕 H 转固定角 GAM
    aw = math.atan2(P2[1] - H_LINK_PIN[1], P2[0] - H_LINK_PIN[0])
    P1 = (H_LINK_PIN[0] + H_LINK_R1 * math.cos(aw + H_LINK_GAM),
          H_LINK_PIN[1] + H_LINK_R1 * math.sin(aw + H_LINK_GAM))

    # h_link 是 arm_link 的子、原点在 H：P2 在 arm 系的方向角就是 aw
    h_ang = -aw
    # dogbone 是 bucket_link 的子、原点在 BUCKET_LUG：必须把 P2 转回 bucket 系
    bx, bz = _rot(P2[0] - ARM_LEN, P2[1], -tk)
    d_ang = -math.atan2(bz - BUCKET_LUG[1], bx - BUCKET_LUG[0])

    # h_link 限位跨 +π，习惯上归到 [1.88, 4.56] 这一段（实测值都在 [0, 2π)）
    return {"lug": lug, "P1": P1, "P2": P2,
            "h_ang": h_ang % (2.0 * math.pi), "d_ang": d_ang}


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


def _links(angles):
    """先解四连杆 —— bucket_cyl 的杆端销挂在它上面，必须先有 P1。"""
    return h_link_state(angles)


def solve(angles):
    """返回 {joint_name: value}：6 个油缸关节 + 2 个四连杆被动关节。

    angles 需要含 swing_joint / boom_joint / arm_joint / bucket_joint
    （swing 不影响缸，仅用于完整性）。
    """
    passives = _links(angles)
    out = {
        "h_link_joint": passives["h_ang"],
        "dogbone_joint": passives["d_ang"],
    }
    for name, cfg in CYLINDERS.items():
        if cfg.get("via") == "h_link":
            ax, az = cfg["A"]
            dx, dz = passives["P1"][0] - ax, passives["P1"][1] - az
        else:
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
    passives = _links(angles)
    res = {}
    for name, cfg in CYLINDERS.items():
        if cfg.get("via") == "h_link":
            ax, az = cfg["A"]
            res[name] = math.hypot(passives["P1"][0] - ax, passives["P1"][1] - az)
        else:
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


def passive_sweep(n=4001):
    """四连杆被动关节：只在 bucket_joint 全行程上密采样（其余主关节不影响它）。

    返回 (h_lo, h_hi, d_lo, d_hi, h_ratio, d_ratio)：
    角度范围 + 相对 bucket_joint 的最大摆速比（用于反推速度限位）。
    """
    lo, hi = LIMITS["bucket_joint"][:2]
    tks = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    hs, ds = [], []
    for tk in tks:
        st = h_link_state({"bucket_joint": tk})
        hs.append(st["h_ang"])
        ds.append(st["d_ang"])

    dt = (hi - lo) / (n - 1)
    h_ratio = max(abs(hs[i + 1] - hs[i]) / dt for i in range(n - 1))
    d_ratio = max(abs(ds[i + 1] - ds[i]) / dt for i in range(n - 1))
    return min(hs), max(hs), min(ds), max(ds), h_ratio, d_ratio


def check_passive(verbose=True):
    """复核四连杆：全行程有解、被动关节不超出限位、速度上限够用。

    速度判据：bucket_joint 按自己的限速跑时，被动关节的最大角速度
    = bucket 限速 × 摆速比，必须 ≤ 该关节的速度限位（否则 rviz 里会追不上，
    更糟的是有人照着限位做规划会算出不可达速度）。
    """
    h_lo, h_hi, d_lo, d_hi, h_ratio, d_ratio = passive_sweep()
    vb = LIMITS["bucket_joint"][2]
    errs = []

    for name, lo, hi in (("h_link_joint", h_lo, h_hi),
                         ("dogbone_joint", d_lo, d_hi)):
        l_lo, l_hi, l_v = LIMITS[name]
        if lo < l_lo - 1e-9 or hi > l_hi + 1e-9:
            errs.append("%s 实测 [%+.4f, %+.4f] 超出限位 [%+.4f, %+.4f]"
                        % (name, lo, hi, l_lo, l_hi))
        peak = vb * (h_ratio if name == "h_link_joint" else d_ratio)
        if peak > l_v + 1e-9:
            errs.append("%s 峰值 %.2f rad/s 超过速度限位 %.2f"
                        % (name, peak, l_v))

    if verbose:
        print("四连杆被动关节（bucket 全行程 4001 帧密采样）")
        print("  关节            实测范围[deg]        摆速比   峰值[rad/s]  限位")
        for name, lo, hi, ratio in (("h_link_joint", h_lo, h_hi, h_ratio),
                                    ("dogbone_joint", d_lo, d_hi, d_ratio)):
            l_lo, l_hi, l_v = LIMITS[name]
            print("  %-14s [%+8.2f, %+8.2f]   %5.3f   %9.2f   "
                  "[%+.4f, %+.4f] v≤%.1f"
                  % (name, math.degrees(lo), math.degrees(hi), ratio,
                     vb * ratio, l_lo, l_hi, l_v))
        print("  " + ("OK" if not errs else "; ".join(errs)))
    return not errs, errs


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
    pok, perrs = check_passive(verbose=verbose)
    return ok and pok, rows


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
