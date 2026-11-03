# S2-07 · ros2 bag 与诊断

> 验证状态：✅ 2026-11-03 在 `ros:humble-ros-base` 容器内实测：20 Hz 发布 → `ros2 bag record` → `ros2 bag info` → `ros2 bag play` → `ros2 topic echo --once` 收到回放消息。

## 1. 现场类比

ROS1 的 bag 用 `rosbag`，ROS2 换成 `ros2 bag`，底层是 SQLite3。带来的变化：

- 可以用 SQL 直接查 bag 内容；
- 支持按 QoS 录制（`--all` 与指定话题行为不同）；
- 回放时如果 QoS 不匹配，**同样会静默收不到**。

## 2. 核心概念

### 2.1 四条命令

| 命令 | 作用 |
|---|---|
| `ros2 bag record -o name /topic` | 录制 |
| `ros2 bag info name` | 查看话题、条数、时长、QoS |
| `ros2 bag play name` | 回放 |
| `ros2 bag convert` | 转格式 / 裁剪 |

### 2.2 录制时的 QoS 问题

`ros2 bag record` 默认会按话题实际 QoS 订阅；但如果话题是 `transient_local`，需要加 `--qos-profile-overrides-path` 才能录到历史消息。**录不到地图/静态参数，八成是这个原因。**

### 2.3 诊断流程

```
1. ros2 bag info        → 有哪些话题、多少条、时长
2. ros2 bag play        → 回放，同时开 ros2 topic hz
3. ros2 topic info -v   → 回放后 QoS 是否匹配
4. ros2 bag info 的 QoS 列 → 与订阅端对比
```

### 2.4 存储位置与体积

- 默认生成 `name.db3` + `metadata.yaml`；
- metadata 丢了，bag 基本废了，**拷走时两个文件一起拷**；
- 高频话题占空间极快，先估 `大小 × 频率 × 时长`。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

ros2 topic pub -r 20 /rl_demo std_msgs/msg/String "{data: x}"
ros2 bag record -o /tmp/demo /rl_demo
ros2 bag info /tmp/demo
ros2 bag play /tmp/demo --rate 0.5
ros2 topic hz /rl_demo
```

## 4. 动手实验

**目标（30 分钟）**：录一段 ROS2 bag 并完整回放验证。

1. 起一个 20 Hz 发布者；
2. `ros2 bag record -o /tmp/demo /rl_demo` 录 20 秒；
3. `ros2 bag info /tmp/demo`，记录时长、条数、QoS；
4. 停掉发布者，`ros2 bag play /tmp/demo`，另开终端 `ros2 topic hz /rl_demo`；
5. 用 `--rate 0.5` 再放一次，对比实测频率。

**通过判据**：能解释「bag 里条数 ≈ 频率 × 时长」，并说出回放时 QoS 不匹配会怎样。

## 5. 自动检查

镜像 `ros:humble-ros-base`，容器需要 `--network host` 让 DDS 发现正常。自包含的录制→回放链路：

```bash
source /opt/ros/humble/setup.bash
(timeout 12 ros2 topic pub -r 20 /rl_demo std_msgs/msg/String "{data: x}" >/dev/null 2>&1 & echo $! >/tmp/pub.pid)
sleep 3 && timeout 5 ros2 bag record -o /tmp/demo /rl_demo
ros2 bag info /tmp/demo
kill $(cat /tmp/pub.pid) 2>/dev/null || true
(timeout 10 ros2 bag play /tmp/demo >/tmp/play.log 2>&1 &)
sleep 1 && ros2 topic echo --once /rl_demo
```

自动检查断言回放后能收到 `data:` 消息，而不是只检查 `ros2 bag --help`。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `bag info` 报 metadata 错误 | metadata.yaml 丢失/损坏 | 重新拷完整目录 |
| 回放后收不到 | QoS 不匹配 | `--qos-profile-overrides-path` 对齐 |
| 录不到静态话题 | 默认 volatile | 覆盖 QoS 为 transient_local |
| bag 体积爆掉 | 录了高频大消息 | 只录必要话题 |
| 回放时间不对 | 需要 `--clock` | 配合 `use_sim_time` |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`C_现场踩坑`、`E_ROS与Linux命令手册`
- 外部参考：ROS 2 Humble rosbag2 文档
- 产出物：一份 ROS2 bag 回放记录（含 hz 对比）

## 9. 下一节

S2-08 · ROS1→ROS2 迁移与 bridge：存量系统怎么过渡。
