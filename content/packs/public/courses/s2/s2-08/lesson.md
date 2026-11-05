# S2-08 · ROS1→ROS2 迁移与 bridge

> 验证状态：✅ 2026-11-04 在 `ros:humble-ros-base` 容器内实测：`ros2 pkg list` 非空，并确认该镜像默认不含 `ros1_bridge`、也没有 ROS1 Noetic 环境。真正的桥接需要 Noetic 与 Humble 共存，未验证。

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

# 安装（Ubuntu 22.04）
sudo apt install ros-humble-ros1-bridge

# 静态桥：只桥指定消息对
ros2 run ros1_bridge dynamic_bridge --bridge-all-topics
```

> ⚠ 上句是**动态桥**示例，仅用于调试；上线请用静态桥配置。

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
