#!/usr/bin/env python3
"""驱动挖掘机 URDF 的关节，按 motion.KEYFRAMES 的挖装循环循环播放。

只在 rviz 里做运动学演示，不含动力学、不含液压模型。

**关键帧只有一份，在 excavator_sim/motion.py**。上一版这个文件里另抄了一套
KEYFRAMES，角度写反了（boom 正负与 kinematics 约定相反）、还不在 LIMITS 内，
结果是"预览图里不穿地、rviz 里斗插进地里"两套数各说各话。现在按时间
`sample(t)` 取帧，和 preview_render / validate_kinematics 完全同源。

发布的关节：
    4 个主动关节  swing / boom / arm / bucket
    6 个油缸关节  <cyl>_pivot_joint（绕 y）+ <cyl>_slide_joint（沿 x）
油缸值由 `cylinders.solve()` 从主关节角反解 —— 缸不是独立自由度，必须跟着
动，否则 rviz 里缸筒和杆停在原位，工作装置在臂头上"空转"。

同时发布 velocity（有限差分），rviz 的 Joint State 面板与 joint_state_publisher
的滑块都能看到真实速度。

用法：
    ros2 run excavator_sim excavator_anim
    ros2 run excavator_sim excavator_anim --ros-args -p speed:=0.5
    # 只要主动关节、不要油缸（例如外接一个自己的求解器）：
    ros2 run excavator_sim excavator_anim --ros-args -p publish_cylinders:=false
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

from .cylinders import solve
from .motion import CYCLE, sample

ACTIVE = ("swing_joint", "boom_joint", "arm_joint", "bucket_joint")


class ExcavatorAnim(Node):

    def __init__(self):
        super().__init__("excavator_anim")
        self.declare_parameter("rate", 30.0)
        self.declare_parameter("speed", 1.0)
        self.declare_parameter("topic", "joint_states")
        self.declare_parameter("publish_cylinders", True)
        self.declare_parameter("start_phase", 0.0)   # 0..1，方便错开相位

        self._rate = max(1.0, float(self.get_parameter("rate").value))
        self._speed = max(0.0, float(self.get_parameter("speed").value))
        self._topic = str(self.get_parameter("topic").value)
        self._with_cyl = bool(self.get_parameter("publish_cylinders").value)
        self._phase0 = float(self.get_parameter("start_phase").value) * CYCLE

        self._pub = self.create_publisher(JointState, self._topic, 10)
        self._t = 0.0
        self._prev = None                # {name: value}，算 velocity 用
        self._prev_wall = None           # 上一次回调的 wall clock（s）
        self._dt = 1.0 / self._rate

        # 定时器用真实时钟推进仿真时间，而不是累加 self._dt：
        # 定时器回调被 rviz 拖慢时，累加会把循环越播越慢（上一版 12 s 的
        # 循环在平板上实测 16 s）。这里按 wall clock 采样，节奏永远对。
        self._wall0 = self.get_clock().now()
        self._timer = self.create_timer(self._dt, self._tick)
        self.get_logger().info(
            "excavator anim: cycle %.1fs, %s at speed=%.2f, %d joints"
            % (CYCLE, self._topic, self._speed,
               4 + (6 if self._with_cyl else 0)))

    def _angles(self, t):
        """t 秒处的完整关节角：主动关节来自 motion.sample，油缸来自反解。"""
        ang = sample(t)
        if self._with_cyl:
            ang.update(solve(ang))
        return ang

    def _tick(self):
        now = self.get_clock().now()
        elapsed = (now - self._wall0).nanoseconds * 1e-9
        self._t = (self._phase0 + elapsed * self._speed) % CYCLE
        ang = self._angles(self._t)

        names = list(ACTIVE) + [n for n in ang if n not in ACTIVE]
        pos = [float(ang[n]) for n in names]

        vel = []
        # 用实测间隔做差分：回调被拖慢时用 self._dt 会把速度报小
        dt = self._dt if self._prev_wall is None else max(elapsed - self._prev_wall, 1e-9)
        self._prev_wall = elapsed
        prev = self._prev
        for n, p in zip(names, pos):
            if prev is None or n not in prev:
                vel.append(0.0)
            else:
                vel.append((p - prev[n]) / dt)
        self._prev = dict(zip(names, pos))

        msg = JointState()
        msg.header.stamp = now.to_msg()
        msg.name = names
        msg.position = pos
        msg.velocity = vel
        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ExcavatorAnim()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
