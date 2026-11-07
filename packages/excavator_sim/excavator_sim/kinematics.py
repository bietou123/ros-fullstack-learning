"""正运动学：给主关节角，算各销轴点与斗齿尖在世界系的位置。

只做演示/校验需要的那几个点 —— 不建完整 TF 树，也不读 URDF。
所有长度、铰点、铲斗几何都来自 design.py，与 gen_meshes.py 生成的
网格是同一组数，所以这里算出来的点就是 rviz 里看到的那几个销。

坐标系：
    base_link  地面中心，x 朝前，y 朝左，z 上
    house      z = HOUSE_Z 处，绕 z 转 swing_joint
    boom       house 系下 (BOOM_PIVOT)，绕 y 转 boom_joint
    arm        boom 系下 (BOOM_LEN, 0)，绕 y 转 arm_joint
    bucket     arm 系下 (ARM_LEN, 0)，绕 y 转 bucket_joint

绕 y 轴转 θ 的约定与 URDF 一致（右手系，y 朝左）：
    x' = x·cosθ + z·sinθ
    z' = −x·sinθ + z·cosθ
⇒ **正角让 +x 方向下垂**。所以 boom_joint 正 = 动臂下压，
arm_joint 正 = 斗杆向机侧收，bucket_joint 正 = 卸料张开。

纯标准库。
"""

from __future__ import annotations

import math

from .cylinders import h_link_state
from .design import (ARM_LEN, BOOM_LEN, BOOM_PIVOT, BUCKET_A1, BUCKET_CX,
                     BUCKET_CZ, BUCKET_LUG, BUCKET_R_OUT, H_LINK_PIN, HOUSE_Z)


def _ry(x, z, th):
    c, s = math.cos(th), math.sin(th)
    return (x * c + z * s, -x * s + z * c)


def _fwd(x, z, th, ox, oz):
    """父系里的 (x,z) → 先绕 y 转 th，再平移 (ox, oz)。"""
    rx, rz = _ry(x, z, th)
    return (ox + rx, oz + rz)


def _swing(x, y, th):
    c, s = math.cos(th), math.sin(th)
    return (x * c - y * s, x * s + y * c)


# 铲斗切削刃中点与齿尖（bucket 系，xz 平面）。齿尖比刃口再沿径向伸出 0.21 m，
# 与 tools/gen_meshes.py 的 gen_bucket_teeth 用的是同一组数。
_COS_A1, _SIN_A1 = math.cos(BUCKET_A1), math.sin(BUCKET_A1)
RIM = (BUCKET_CX + BUCKET_R_OUT * _COS_A1, BUCKET_CZ + BUCKET_R_OUT * _SIN_A1)
TOOTH_TIP = (RIM[0] + 0.21 * _COS_A1, RIM[1] + 0.21 * _SIN_A1)


def fk(angles):
    """返回世界系下的关键点（m）。

    angles 需含 swing_joint / boom_joint / arm_joint / bucket_joint。
    返回 dict：boom_pivot / boom_head / arm_head / bucket_lug /
    bucket_rim / tooth_tip / arm_back / h_link_pin / h_link_p1 / dog_pin
    （各为 (x, y, z)）。后三个是铲斗四连杆的销，由 cylinders 闭式解算。
    """
    sb = angles.get("swing_joint", 0.0)
    tb = angles["boom_joint"]
    ta = angles["arm_joint"]
    tk = angles["bucket_joint"]

    px, pz = BOOM_PIVOT[0], BOOM_PIVOT[2]

    def to_world(xz_house):
        x, y = _swing(xz_house[0], 0.0, sb)
        return (x, y, HOUSE_Z + xz_house[1])

    # arm 系原点在 boom 系 (BOOM_LEN, 0)
    arm_org = (BOOM_LEN, 0.0)
    # bucket 系原点在 arm 系 (ARM_LEN, 0)，再变换到 boom 系
    bkt_org = _fwd(ARM_LEN, 0.0, ta, arm_org[0], arm_org[1])

    def bkt_to_boom(x, z):
        # bucket → arm（绕 y 转 tk，再加 arm 系原点偏移）→ boom（转 ta，加 boom 系原点）
        ax, az = _ry(x, z, tk)
        return _fwd(ax + ARM_LEN, az, ta, arm_org[0], arm_org[1])

    def bkt_to_house(x, z):
        bx, bz = bkt_to_boom(x, z)
        return _fwd(bx, bz, tb, px, pz)

    def arm_to_house(x, z):
        bx, bz = _fwd(x, z, ta, arm_org[0], arm_org[1])
        return _fwd(bx, bz, tb, px, pz)

    arm_back_boom = _fwd(-0.16, 0.0, ta, arm_org[0], arm_org[1])

    # 四连杆的两个销（H-link 的 P1、dogbone 的 P2）由 cylinders 闭式解开，
    # 保证 fk 和 anim_node 发布的角度是同一组数，不会各算各的。
    link = h_link_state({"bucket_joint": tk})

    pts_house = {
        "boom_pivot": (px, pz),
        "boom_head": _fwd(BOOM_LEN, 0.0, tb, px, pz),
        "arm_head": _fwd(bkt_org[0], bkt_org[1], tb, px, pz),
        "bucket_lug": bkt_to_house(*BUCKET_LUG),
        "bucket_rim": bkt_to_house(*RIM),
        "tooth_tip": bkt_to_house(*TOOTH_TIP),
        "arm_back": _fwd(arm_back_boom[0], arm_back_boom[1], tb, px, pz),
        "h_link_pin": arm_to_house(*H_LINK_PIN),
        "h_link_p1": arm_to_house(*link["P1"]),
        "dog_pin": arm_to_house(*link["P2"]),
    }
    return {k: to_world(v) for k, v in pts_house.items()}


if __name__ == "__main__":
    import sys
    b = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    a = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    k = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    for name, p in fk({"swing_joint": 0.0, "boom_joint": b,
                       "arm_joint": a, "bucket_joint": k}).items():
        print("%-11s x=%+7.3f y=%+7.3f z=%+7.3f" % (name, p[0], p[1], p[2]))
