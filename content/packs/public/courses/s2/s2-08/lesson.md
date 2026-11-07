# S2-08 · ROS1→ROS2 迁移与 bridge

> 验证状态：✅ 2026-11-06 在 GitHub Actions 的官方镜像 `ros:foxy-ros1-bridge`（内含 Noetic + Foxy）中实测**双向桥接**：ROS1 `rostopic pub /chatter` → ROS2 `ros2 topic echo` 收到 `data: from_ros1`；ROS2 `ros2 topic pub /chatter2` → ROS1 `rostopic echo` 收到 `data: "from_ros2"`；`dynamic_bridge --bridge-all-topics` 日志同时记录两个方向的 `Passing message from …`，脚本最终输出 `ROS1_BRIDGE_OK`（run `42179975578`）。✅ 2026-11-04 另确认 `ros:humble-ros-base` 默认不含 `ros1_bridge`、也没有 Noetic 环境。⚠ Humble + Noetic（Ubuntu 22.04）共存需源码编译，**未实测**；服务桥与自定义消息对也**未实测**。

## 1. 现场类比

存量车端是 ROS1，新算法在 ROS2 上开发。全量重写风险太高，现实做法是：

**先架桥让两边通起来，再按模块逐步迁移。**

桥不是永久方案：它增加一个进程、一层延迟、一类新故障。**迁移的目标永远是「拆掉桥」。**

## 2. 核心概念

### 2.1 迁移对照表

| 概念 | ROS1 | ROS2 | 迁移注意 |
|---|---|---|---|
| 中间件 | TCPROS | DDS | QoS 要重新设计 |
| 构建 | catkin | colcon / ament | 目录与依赖声明重写 |
| 节点 API | rospy / roscpp | rclpy / rclcpp | 回调与生命周期不同 |
| launch | XML | Python | 参数机制不同 |
| 时间 | `rospy.Time` | `rclpy.time.Time` + 时钟源 | `use_sim_time` 语义更严格 |
| 参数 | 参数服务器 | 节点参数 | 没有全局服务器 |

### 2.2 ros1_bridge 的两种模式

| 模式 | 行为 | 适用 |
|---|---|---|
| 静态桥 | 只为编译时指定的消息对建桥 | 生产，可控 |
| 动态桥 | 运行时按需加载 | 调试，方便但不可预测 |

**现场上线用静态桥**：动态桥的「按需加载」会在关键时刻引入未知延迟。

### 2.3 桥的三个硬约束

1. **需要双 ROS 环境**：同一台机器同时 source Noetic 与 Humble，环境变量极易冲突；
2. **消息类型必须一致**：`.msg` 定义不同（字段/类型）就桥不过去；
3. **只桥消息，不桥服务**（默认）；服务桥需要用 `rospy`/`rclpy` 另行处理。

### 2.4 迁移顺序建议

```
1. 只读数据先迁（传感器、状态）→ 桥单向
2. 控制输出后迁（指令）→ 桥双向，加看门狗
3. 最后迁核心算法 → 拆桥
```

每步都要有回滚方案：**旧版本必须能随时切回去**。

## 3. 可复制命令 / 代码

```bash
# 环境检查（两边都要有）
ls /opt/ros/noetic/setup.bash /opt/ros/humble/setup.bash

# ROS2 侧确认桥包是否安装
ros2 pkg list | grep ros1_bridge

# ⚠ Humble 没有现成的 ros1_bridge 二进制包（它必须与 Noetic 在同一机器上编译），
#    `sudo apt install ros-humble-ros1-bridge` 不成立；教材实测走的是官方镜像
#    ros:foxy-ros1-bridge（Noetic + Foxy 已预装并编好桥）。

# 动态桥：自动桥接所有话题（仅调试用）
ros2 run ros1_bridge dynamic_bridge --bridge-all-topics
```

> 2026-11-06 在 `ros:foxy-ros1-bridge` 容器内实测（CI workflow `verify-ros1-bridge`，run `42179975578`）：
>
> 1. 容器内启动 `roscore`，再启动 `dynamic_bridge --bridge-all-topics`；
> 2. **先**在 ROS2 侧起 `ros2 topic echo /chatter std_msgs/msg/String`，**再**在 ROS1 侧 `rostopic pub -r 2 /chatter std_msgs/String 'data: from_ros1'`；
> 3. ROS2 侧收到 3 条 `data: from_ros1`，`ros2 topic list -t` 中出现 `/chatter [std_msgs/msg/String]`；
> 4. 反向起 `ros2 topic pub -r 2 /chatter2` 后，ROS1 `rostopic echo -n1 /chatter2` 收到 `data: "from_ros2"`；
> 5. 桥日志同时出现 `Passing message from ROS 1 std_msgs/String to ROS 2 std_msgs/msg/String` 与 `Passing message from ROS 2 std_msgs/msg/String to ROS 1 std_msgs/String`。
>
> **顺序很重要**：ROS2 订阅端必须先起来。第一次 CI 运行中订阅端晚于发布端启动，桥日志已经记录消息通过，但 `ros2 topic echo` 一条都没接住，误报「未收到」。Foxy 的 `ros2 topic echo` 也没有 `--once`，只能用 `timeout` + 轮询输出文件。
>
> 一键复跑：`bash scripts/verify-ros1-bridge.sh`，或手动触发 GitHub Actions 的 `verify-ros1-bridge` workflow（需能拉 `ros:foxy-ros1-bridge` 镜像）。

## 4. 动手实验

**目标（45 分钟）**：写一份本项目的迁移评估表（不要求真的跑桥）。

1. 列出你负责的节点，按「只读 / 控制 / 核心算法」分类；
2. 对每个节点标注：消息类型是否已存在 ROS2 版本、QoS 需求、启停依赖；
3. 标出哪些节点必须走桥、哪些可以直接重写；
4. 写出「第一阶段只迁什么」以及「出问题时怎么回滚」；
5. 检查是否有全局参数依赖——这是 ROS2 里必须重设计的部分。

**通过判据**：迁移表里每个节点都有「迁移方式 + 风险 + 回滚」三列，不能只写「迁」。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && ros2 pkg list | grep -c ros1_bridge
source /opt/ros/humble/setup.bash && ros2 pkg list | head -n 5
```

`ros:humble-ros-base` 默认**不含** `ros1_bridge`，`grep -c` 返回 0 属于预期；需要桥请按第 3 节在完整环境安装。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 桥启动了但话题不通 | 两边环境变量互相污染 | 分开 shell，显式 source |
| 桥日志显示已通过，接收端却没收到 | 订阅端起得比发布端晚，错过了发现窗口 | 先起订阅再起发布，或延长等待时间 |
| 消息桥不过去 | `.msg` 定义不一致 | 对齐字段名与类型 |
| 延迟突然增大 | 动态桥按需加载 | 改静态桥 |
| 时间戳乱 | 两边时钟/`use_sim_time` 不一致 | 统一时钟源 |
| 迁移后参数失效 | 依赖全局参数服务器 | 改为节点参数 + yaml |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 外部参考：ROS 2 Humble ros1_bridge 文档
- 产出物：本项目迁移评估表（节点 / 方式 / 风险 / 回滚）

## 9. 下一节

S3-01 · CAN 总线与帧结构：从 ROS 话题走到车上的一根线。
