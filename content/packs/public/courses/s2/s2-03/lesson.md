# S2-03 · rclpy 节点与 QoS

> 验证状态：⚠ 本机未安装 ROS2，本课命令**未在本机执行**。实验使用 `ros:humble-ros-base` 容器（`--network host`）。

## 1. 现场类比

ROS1 里「发出去就发出去」，收不到就是没发。ROS2 里同一句发布，可能因为**服务质量（QoS）**设置不同而丢消息，而且**双方不报错**。

现场最典型：传感器用 `best_effort` 发，订阅端用 `reliable` 收 → **完全静默地收不到**。这不是 bug，是 DDS 的兼容规则。

## 2. 核心概念

### 2.1 QoS 的四个关键项

| 项 | 取值 | 现场含义 |
|---|---|---|
| Reliability | reliable / best_effort | 要不要重传 |
| Durability | transient_local / volatile | 晚加入的订阅者能否收到历史 |
| History | keep_last(n) / keep_all | 缓存多少 |
| Deadline | 周期约定 | 超过就触发事件 |

### 2.2 兼容性规则（必背）

| 发布者 | 订阅者 | 结果 |
|---|---|---|
| reliable | reliable | ✅ |
| reliable | best_effort | ✅（订阅端主动降级） |
| best_effort | best_effort | ✅ |
| best_effort | reliable | ❌ **静默不匹配** |

**reliable 订阅者要求每一帧都到，best_effort 发布者做不到 → 不建连。** 调试时先 `ros2 topic info -v` 看双方 QoS。

### 2.3 选型建议

| 数据 | 推荐 QoS | 原因 |
|---|---|---|
| 手柄/控制指令 | reliable, keep_last(1) | 必须到，旧的没意义 |
| 高频传感器 | best_effort, keep_last(5) | 丢一两帧可接受，延迟优先 |
| 地图/静态配置 | transient_local, keep_last(1) | 晚启动的节点也要拿到 |

### 2.4 rclpy 最小节点

```python
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

class Pub(Node):
    def __init__(self):
        super().__init__("rl_pub")
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.pub = self.create_publisher(String, "/rl_chat", qos)
        self.create_timer(0.2, self.tick)

    def tick(self):
        self.pub.publish(String(data="hi"))

def main():
    rclpy.init()
    node = Pub()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

ros2 topic pub -r 5 /rl_demo std_msgs/msg/String "{data: hi}" \
  --qos-reliability best_effort --qos-depth 5
ros2 topic info -v /rl_demo
ros2 topic echo /rl_demo --qos-reliability reliable
ros2 topic hz /rl_demo
```

## 4. 动手实验

**目标（40 分钟）**：造一次「静默收不到」，再修好。

1. 终端 A 用 `--qos-reliability best_effort` 发布；
2. 终端 B 用 `--qos-reliability reliable` echo，记录现象（无输出、无报错）；
3. `ros2 topic info -v /rl_demo` 看双方 QoS；
4. 把 B 改成 `best_effort`，恢复正常；
5. 把 A 改成 `reliable`，B 保持 reliable，再验证。

**通过判据**：能不看笔记写出「哪种组合不匹配」，并用 `topic info -v` 给出证据。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && python3 -c "import rclpy; print(rclpy.__file__)"
source /opt/ros/humble/setup.bash && ros2 topic pub --help 2>&1 | grep -q qos-reliability
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 发布有、echo 无 | QoS 不兼容 | `topic info -v` 比对 |
| 晚启动的节点收不到历史 | 用了 volatile | 需要历史的改 `transient_local` |
| 高频数据延迟累积 | reliable + 大队列 | 改 best_effort + keep_last(小) |
| 节点崩溃无提示 | 回调异常被吞 | 打开日志、加 try/except |
| `rclpy.init()` 二次调用 | 多次初始化 | 只初始化一次，finally 里 shutdown |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 外部参考：ROS 2 Humble QoS 文档
- 产出物：QoS 对照表（数据类型 → QoS 选择及理由）

## 9. 下一节

S2-04 · service 与 action：长任务怎么做得可取消、可反馈。
