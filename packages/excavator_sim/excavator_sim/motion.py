"""姿态与动画关键帧：单一来源。

preview_render / anim_node / validate_kinematics 都从这里取，避免"预览图里
不穿地、rviz 里穿地"这种两套数各说各话的事故。

命名约定（与 kinematics / cylinders 一致）：
    swing_joint   绕 z，俯视逆时针
    boom_joint    绕 y，**正 = 下压**（负 = 抬臂）
    arm_joint     绕 y，**正 = 向机侧收**
    bucket_joint  绕 y，**正 = 卸料张开**（负 = 收斗）

所有姿态都在 LIMITS 内、齿尖不穿地（validate_kinematics.py 会逐帧复核）。
上面这些角度是归一化估计的演示值，不是 OEM 的作业姿态表。

纯标准库。
"""

from __future__ import annotations

from .design import ARM_LEN, BOOM_LEN
from .kinematics import fk

# ---------------------------------------------------------------------------
# 静态姿态（交给 preview_render 出三视图 / 交给文档配图）
# ---------------------------------------------------------------------------
# 这三个是"看得懂在干什么"的姿态，不是随便摆的角度 0：
#
#   transport  行走/抬举：动臂抬 34°，斗杆折回，斗口收拢。整机最高点 = 斗背，
#              齿尖离地 1.33 m，前后都收在回转半径内，是真实挖机转场时抬着走
#              的样子（斗要离地远一点，过沟埂不磕）。
#   park       停放/怠速：动臂只抬 8.6°，斗杆大折角收拢（146°），斗口朝下收紧，
#              **齿尖离地 0.27 m**。整机轮廓：总长 9.79 m、最高点 3.25 m、
#              高/长 = 0.333 —— 真机（20 t 级）转场/停放正好是 9.6 m × 3.0~3.2 m，
#              这个比例才对得上。评审拼图的归一化剪影测量量的就是这一档。
#              上一版是 boom -0.40（抬 23°）配斗杆 2.30：动臂抬得高、斗杆伸得直，
#              总长被撑到 9.42 m 而最高点跑到 4.47 m，高/长 0.476 —— 像台吊车，
#              不像停在平地上的挖机。
#   dig        掘削：动臂抬 17°，斗杆折 83°，斗口微开，**齿尖刚好贴地 0.05 m**，
#              铲斗在履带前方 5.6 m 处 —— 这一条约束是"斗不能插进地面"的锚点。
#   lift       高举：动臂抬 43°，整条工作装置离地 2.79 m，用来看臂背轮廓和
#              油缸在极限附近的姿态。
#
# 早期直接用 (0,0,0) 当"零位图"是错的：那样动臂水平、斗杆直伸，齿尖在
# 10.7 m 外、离地 1.4 m，看着像吊车不像挖机；而把斗杆折到 2.35 rad 又会
# 把铲斗压进地里 0.70 m。
STATIC_POSES = {
    "transport": {"swing_joint": 0.00, "boom_joint": -0.60,
                  "arm_joint": 2.30, "bucket_joint": -0.30},
    "park": {"swing_joint": 0.00, "boom_joint": -0.15,
             "arm_joint": 2.55, "bucket_joint": -0.45},
    "dig": {"swing_joint": 0.00, "boom_joint": -0.30,
            "arm_joint": 1.45, "bucket_joint": 0.30},
    "lift": {"swing_joint": 0.00, "boom_joint": -0.75,
             "arm_joint": 1.55, "bucket_joint": 0.55},
}

# ---------------------------------------------------------------------------
# 动画关键帧：一个"挖—回转—卸—回位"循环，约 12 s
# ---------------------------------------------------------------------------
# 只列关键姿态，anim_node 在相邻两帧之间线性插值。swing 用 0 → +1.20 rad
# （69°）而不是满行程 ±π，是因为演示镜头固定在 3/4 视，转太多工作装置会转
# 到机身后侧看不见。
#
# 抬臂（boom 变负）必须先于折斗杆（arm 变大）：动臂水平时斗杆折角超过 2.2 rad
# 铲斗会挖穿地面。表中回位段先收臂再放低，就是为了保住这条。
#
# 时间轴同时受**速度限位**约束：线性插值下每段速度 = Δ角/Δ段长，必须低于
# URDF 的 <limit velocity>（bucket 1.8 rad/s、slide 1.0439 m/s 等）。上一版
# 卸料段 1.0 s 内抖 1.95 rad，峰值 1.95 rad/s、带动斗缸杆 1.27 m/s，两项都
# 超限 —— 在真机上意味着液压缸跑到极限流量之外。这不是"测试太严"，所以
# 解法是拉长卸料段（1.0 s → 1.4 s，峰值降到 1.39 rad/s），不是放宽限位。
KEYFRAMES = [
    (0.0, {"swing_joint": 0.00, "boom_joint": -0.60,
           "arm_joint": 2.30, "bucket_joint": -0.30}),   # 待命
    (1.6, {"swing_joint": 0.00, "boom_joint": -0.35,
           "arm_joint": 1.60, "bucket_joint": 0.35}),    # 伸臂下斗，斗口张开
    (3.0, {"swing_joint": 0.00, "boom_joint": -0.32,
           "arm_joint": 1.48, "bucket_joint": -1.00}),   # 收斗挖掘
    (4.4, {"swing_joint": 0.00, "boom_joint": -0.55,
           "arm_joint": 1.55, "bucket_joint": -1.05}),   # 提臂离地
    (6.2, {"swing_joint": 1.20, "boom_joint": -0.80,
           "arm_joint": 1.55, "bucket_joint": -1.05}),   # 回转
    (7.6, {"swing_joint": 1.20, "boom_joint": -0.85,
           "arm_joint": 1.35, "bucket_joint": 0.90}),    # 卸料张斗
    (8.8, {"swing_joint": 1.20, "boom_joint": -0.75,
           "arm_joint": 1.45, "bucket_joint": -0.20}),   # 收斗
    (10.4, {"swing_joint": 0.00, "boom_joint": -0.80,
            "arm_joint": 1.55, "bucket_joint": -0.30}),  # 回转归位
    (12.4, {"swing_joint": 0.00, "boom_joint": -0.60,
            "arm_joint": 2.30, "bucket_joint": -0.30}),  # 回到起点
]

CYCLE = KEYFRAMES[-1][0]

_CHECK_POINTS = ("tooth_tip", "bucket_rim", "bucket_lug", "arm_head", "arm_back")


def sample(t):
    """按时间 t（s）在 KEYFRAMES 间线性插值，返回关节角 dict。

    循环播放：t 超出 [0, CYCLE) 时自动取模。
    """
    t = t % CYCLE
    for i in range(len(KEYFRAMES) - 1):
        t0, a0 = KEYFRAMES[i]
        t1, a1 = KEYFRAMES[i + 1]
        if t0 <= t <= t1:
            u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return {k: a0[k] + (a1[k] - a0[k]) * u for k in a0}
    return dict(KEYFRAMES[-1][1])


def lowest_point(angles):
    """返回该姿态下工作装置的最低点高度（m，世界系）。"""
    p = fk(angles)
    return min(p[m][2] for m in _CHECK_POINTS)


def check_poses(samples=0, verbose=True):
    """复核静态姿态与关键帧：关节在限位内、齿尖不穿地。

    这不是"测试能不能过"的软指标 —— 齿尖穿地就是 rviz 里铲斗藏进地面的
    视觉 bug，必须靠改姿态解决，不许放宽判据。
    """
    from .cylinders import LIMITS, solve

    problems = []

    def one(tag, ang):
        for name in ("boom_joint", "arm_joint", "bucket_joint"):
            lo, hi, _ = LIMITS[name]
            v = ang[name]
            if v < lo - 1e-9 or v > hi + 1e-9:
                problems.append("%s: %s=%.3f 超出 [%.2f, %.2f]"
                                % (tag, name, v, lo, hi))
        lo, hi, _ = LIMITS["swing_joint"]
        if not (lo <= ang["swing_joint"] <= hi):
            problems.append("%s: swing 超出限位" % tag)
        z = lowest_point(ang)
        if z < -1e-6:
            problems.append("%s: 最低点 z=%.3f 穿地" % (tag, z))
        # 油缸长度必须落在 Lmax 附近留余量（solve 给 slide，slide ≤ 0）
        for k, v in solve(ang).items():
            if k.endswith("_slide_joint") and v > 1e-9:
                problems.append("%s: %s 超出 Lmax %.4f" % (tag, k, v))
        return z

    if verbose:
        print("%-22s %9s %9s %9s   tip(x,z)          minz" % (
            "pose", "boom", "arm", "bucket"))
    for name, ang in STATIC_POSES.items():
        z = one(name, ang)
        p = fk(ang)["tooth_tip"]
        if verbose:
            print("%-22s %+9.2f %+9.2f %+9.2f   (%+5.2f,%+5.2f)   %+5.2f" % (
                name, ang["boom_joint"], ang["arm_joint"],
                ang["bucket_joint"], p[0], p[2], z))

    if samples:
        dz = float("inf")
        for i in range(samples):
            t = CYCLE * i / samples
            ang = sample(t)
            z = one("keyframe t=%.2f" % t, ang)
            dz = min(dz, z)
        if verbose:
            print("%-22s %9s %9s %9s   %21s   %+5.2f" % (
                "keyframes(%d 采样)" % samples, "", "", "", "", dz))

    if verbose:
        print()
        if problems:
            for p in problems:
                print("  ✗ " + p)
        else:
            print("  全部姿态在限位内且不穿地")
    return not problems, problems


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    ok, probs = check_poses(samples=n)
    raise SystemExit(0 if ok else 1)
