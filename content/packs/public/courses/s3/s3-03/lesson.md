# S3-03 · TF2 广播器与监听器

> 验证状态：✅ 2026-11-04 在 `ros:humble-ros-base` 容器内实测（`--network host`）：`static_transform_publisher` 发布后 `tf2_echo` 输出平移 `0.000, 0.000, 1.000`，`ros2 topic echo /tf_static --once` 收到 `boom_base`。

## 1. 现场类比

S1-07 用的是命令行工具，这一节是自己写代码发 TF。差别在于：**现场数据要实时灌进坐标树**——关节角编码器每 20ms 更新一次，TF 也必须跟着更新。

写错了会怎样：模型看起来在动，但和实车不是一个姿势；或者 TF 发布频率太低，RViz 一卡一卡。

## 2. 核心概念

### 2.1 广播器（Broadcaster）

```python
import rclpy
from rclpy.node import Node
from tf2_ros import TransformBroadcaster
from geometry_msgs.msg import TransformStamped
import math

class ArmTf(Node):
    def __init__(self):
        super().__init__("arm_tf")
        self.br = TransformBroadcaster(self)
        self.create_timer(0.02, self.tick)   # 50 Hz

    def tick(self):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = "base_link"
        t.child_frame_id = "arm_link"
        t.transform.translation.x = 0.0
        t.transform.translation.y = 0.0
        t.transform.translation.z = 0.5
        # 示例角度：绕 Y 轴 30°
        a = math.radians(30.0) / 2.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = math.sin(a)
        t.transform.rotation.z = 0.0
        t.transform.rotation.w = math.cos(a)
        self.br.sendTransform(t)
```

**四元数不是欧拉角**：绕单轴旋转 θ 时，分量是 `sin(θ/2)`，不是 `sin(θ)`。

### 2.2 监听器（Listener）

```python
import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener

class TfQuery(Node):
    def __init__(self):
        super().__init__("tf_query")
        self.buf = Buffer()
        self.listener = TransformListener(self.buf, self)

    def lookup(self, a, b):
        try:
            t = self.buf.lookup_transform(a, b, rclpy.time.Time())
            self.get_logger().info(f"{a} -> {b}: {t.transform.translation}")
        except Exception as e:
            self.get_logger().warn(str(e))
```

`lookup_transform(源, 目标)` 的方向是**从目标到源**的变换，名字方向搞反是最常见的 bug。

### 2.3 频率与时间戳

| 项目 | 建议 | 理由 |
|---|---|---|
| 发布频率 | ≥ 控制频率 | 低于控制频率，插值误差变大 |
| 时间戳 | 用 `get_clock().now()` | 仿真时必须用仿真时钟 |
| 静态部分 | 用 `/tf_static` | 避免每帧重复发送 |

### 2.4 查询失败的三种原因

1. 框架名不存在（拼写/命名空间）；
2. 时间戳超界（`lookup_transform` 的时间参数超出缓存）；
3. 树不连通（中间某一环没人发）。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

ros2 run tf2_ros static_transform_publisher --x 0 --y 0 --z 1 \
  --frame-id base_link --child-frame-id boom_base

ros2 run tf2_ros tf2_echo base_link boom_base
ros2 topic hz /tf
ros2 topic echo /tf_static
```

## 4. 动手实验

**目标（40 分钟）**：写一个 50 Hz 广播器 + 一个查询节点。

1. 用 2.1 的代码起广播器，`ros2 topic hz /tf` 确认频率；
2. 用 `tf2_echo` 查询，核对平移量；
3. 写查询节点，每秒打印一次变换；
4. 把发布频率降到 5 Hz，观察查询是否出现等待；
5. 故意把 `child_frame_id` 改错，记录报错原文。

**通过判据**：能解释「为什么四元数用 sin(θ/2)」，并能说出三类查询失败的区分方法。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && rospack find tf2_ros 2>/dev/null || ros2 pkg list | grep -c tf2_ros
source /opt/ros/humble/setup.bash && python3 -c "import tf2_ros; print('ok')"
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `LookupException` | 框架名不存在 | `view_frames` 核对 |
| `ExtrapolationException` | 时间戳超界 | 用最新时间或扩大缓存 |
| 模型抽搐 | 发布频率低且时间戳跳变 | 提高频率、统一时钟 |
| 方向反了 | lookup 源/目标顺序反 | 明确「A 看 B」写法 |
| 仿真里全乱 | 未用仿真时钟 | `use_sim_time` + `--clock` |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s3
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS 2 tf2 教程（Broadcaster / Listener）
- 产出物：50 Hz 广播器 + 查询工具与日志

## 9. 下一节

S3-04 · RViz 与 robot_state_publisher：把 URDF 和 TF 串起来。
