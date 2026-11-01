# S2-01 · ROS2 架构：DDS 与节点发现

> 验证状态：⚠ 本机未安装 ROS2，本课命令**未在本机执行**。实验使用 `ros:humble-ros-base` 容器（`--network host`，DDS 发现需要真实网卡/组播）。

## 1. 现场类比

ROS1 像「公司总机」：所有人先打总机登记，总机记不住，全公司失联。

ROS2 像「对讲机」：开机自己喊一声「我在」，周围能听见的自动建联。**没有中心，但依赖大家在同一频道**——频道号是 `ROS_DOMAIN_ID`，喊不远就是组播被网络挡了。

现场最常见的 ROS2 故障不是代码错，而是「两个终端不在同一个域 / 组播被交换机过滤」。

## 2. 核心概念

### 2.1 ROS2 的三层

| 层 | 组件 | 作用 |
|---|---|---|
| 用户 API | rclpy / rclcpp | 写节点的接口 |
| 中间件抽象 | rmw | 统一不同 DDS 实现的接口 |
| 传输 | DDS（Fast DDS / Cyclone DDS） | 发现、收发、QoS |

DDS 负责「谁在、发什么、怎么保证送到」，这就是 ROS2 不再需要 master 的原因。

### 2.2 发现（Discovery）为什么在现场容易失败

- **组播**：默认靠 UDP 组播发现，很多工业交换机关组播；
- **防火墙**：默认放行端口范围有限（不同 DDS 实现端口不同）；
- **多网卡**：机器上有 Wi-Fi、以太网、虚拟网卡时，DDS 可能从错的网卡出去；
- **域号**：`ROS_DOMAIN_ID` 不同 = 不同频道，彼此看不见。

排查顺序：**同机能否互见 → 跨机能否互见 → 换网卡是否正常 → 域号是否一致**。

### 2.3 与 ROS1 的对应关系

| 项目 | ROS1 | ROS2 |
|---|---|---|
| 发现 | `roscore` | DDS 自动发现 |
| 环境变量 | `ROS_MASTER_URI` | `ROS_DOMAIN_ID`、`RMW_IMPLEMENTATION` |
| 列节点 | `rosnode list` | `ros2 node list` |
| 列话题 | `rostopic list` | `ros2 topic list` |

### 2.4 只为同机通信时

调试可以用 `ROS_LOCALHOST_ONLY=1`（Humble 起支持），让发现只在本地，避免被现场网络干扰。**但上线时一定要确认它就应当是开着的**，否则跨机通信会「莫名其妙不通」。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

echo $ROS_DISTRO            # humble
ros2 node list
ros2 topic list
ros2 topic list -t          # 带类型
ros2 daemon stop            # CLI 卡住时先停守护进程

# 只在本机发现（调试用）
export ROS_LOCALHOST_ONLY=1
```

## 4. 动手实验

**目标（30 分钟）**：在一台机器上验证「发现」是否正常。

1. 终端 A：`ros2 topic pub -r 5 /rl_demo std_msgs/msg/String "{data: hi}"`；
2. 终端 B：`ros2 node list`、`ros2 topic list -t`，确认能看到；
3. 终端 B：`ros2 topic echo /rl_demo`，确认内容；
4. 把 B 的 `ROS_DOMAIN_ID` 改成 1 再试，记录现象；
5. 恢复后设 `ROS_LOCALHOST_ONLY=1`，再试一次并记录差异。

**通过判据**：能解释「为什么换个域号就什么都看不到」，并能说出至少两种导致跨机发现失败的现场原因。

## 5. 自动检查

镜像 `ros:humble-ros-base`，网络 host：

```bash
source /opt/ros/humble/setup.bash && echo $ROS_DISTRO
source /opt/ros/humble/setup.bash && ros2 topic list -t | head
```

预期输出 `humble` 与话题列表（至少包含参数事件话题）。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `ros2 node list` 为空 | 域号不同 / 组播被挡 | 统一 `ROS_DOMAIN_ID`，查交换机 |
| CLI 卡住不返回 | daemon 状态异常 | `ros2 daemon stop && ros2 daemon start` |
| 一会儿能看见一会儿看不见 | 多网卡选错出口 | 绑网卡或 `ROS_LOCALHOST_ONLY` |
| 换 DDS 实现后不通 | `RMW_IMPLEMENTATION` 不一致 | 全部节点统一 |
| 跨机只能单向通信 | 防火墙单向放行 | 双向放开 DDS 端口段 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS 2 Humble 文档（Discovery / DDS / QoS）
- 产出物：发现机制实验记录（域号、网络、可见性）

## 9. 下一节

S2-02 · colcon 工作空间与包：ROS2 的构建方式。
