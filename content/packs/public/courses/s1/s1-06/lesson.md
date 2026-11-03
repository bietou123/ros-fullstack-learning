# S1-06 · rosbag 录制与回放

> 验证状态：✅ 2026-11-03 在 `ros:noetic-ros-base` 容器内实测：启动 roscore → 20 Hz 发布 → `rosbag record` → `rosbag info` → `rosbag play` → `rostopic echo` 收到回放消息，整条链路在单容器内完成。

## 1. 现场类比

现场问题「只有那一分钟会复现」。等人赶到，现象早没了。

rosbag 的价值是把**那一分钟原封不动装进文件**：话题、消息、时间戳全部保留，回去可以反复回放、离线分析、发给同事。

**不会用 bag 的现场工程师，只能靠描述问题；会用的，能直接让别人看到问题。**

## 2. 核心概念

### 2.1 四条命令

| 命令 | 作用 | 现场用法 |
|---|---|---|
| `rosbag record -O x.bag /a /b` | 录指定话题 | 只录需要的，别 `-a` |
| `rosbag info x.bag` | 看话题、条数、时长 | 交接前先 info 一遍 |
| `rosbag play x.bag` | 按时间戳回放 | 配合 `--rate` 调速 |
| `rosbag filter` | 按条件裁剪 | 去掉无关话题减体积 |

### 2.2 该录什么

一条最小可复盘的远控 bag 至少包含：

```
原始输入（手柄/指令）
控制输出（CAN 帧或 cmd）
反馈（姿态、压力、角度）
/tf（坐标系关系）
/rosout（日志）
```

只录「控制输出」的 bag，回放时看不出**为什么**输出是这个值。

### 2.3 体积与时间

- 高频大消息（点云、图像）会让 bag 膨胀很快：先算 `消息大小 × 频率 × 秒数`；
- `-b` 调整缓存，磁盘满时 bag 会写坏；
- 回放默认按原始时间戳，`rosbag play --rate 0.5` 可放慢，便于观察；
- 回放前**必须关掉真机节点**，否则仿真指令会和实车指令同时下发。

> ⚠ 高危：在实车上回放含控制话题的 bag，等于给车发了一次真实指令。回放前必须确认执行层已断开或处于安全状态。

### 2.4 bag 的隐私

bag 里可能包含现场 IP、设备名、画面。**对外发送前必须筛话题**，与 Sensitive 数据规则一致。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/noetic/setup.bash

rosbag record -O /tmp/demo.bag /rl_demo /rosout
rosbag info /tmp/demo.bag
rosbag play /tmp/demo.bag --rate 0.5
rosbag filter /tmp/demo.bag /tmp/only_demo.bag 'topic == "/rl_demo"'
```

## 4. 动手实验

**目标（30 分钟）**：录一段、查一段、回放一段。

1. `roscore`，并起一个 20 Hz 的话题；
2. `rosbag record -O /tmp/demo.bag /rl_demo /rosout` 录 30 秒后 Ctrl-C；
3. `rosbag info /tmp/demo.bag`，记录时长、消息数、平均频率；
4. `rosbag play /tmp/demo.bag`，另开终端 `rostopic hz /rl_demo` 对比回放频率；
5. 用 `filter` 裁掉 `/rosout`，比较两个文件大小。

**通过判据**：能说出 bag 时长与消息条数的关系，并解释为什么回放前要断开执行层。

## 5. 自动检查

镜像 `ros:noetic-ros-base`。单容器内可以同时跑 master、发布者、录制与回放，下面是一条自包含的完整链路：

```bash
source /opt/ros/noetic/setup.bash
(roscore >/tmp/rc.log 2>&1 &) && sleep 6
(timeout 10 rostopic pub -r 20 /rl_demo std_msgs/String "data: x" >/dev/null 2>&1 & echo $! >/tmp/pub.pid)
sleep 1 && timeout 5 rosbag record -O /tmp/demo.bag /rl_demo
rosbag info /tmp/demo.bag
kill $(cat /tmp/pub.pid) 2>/dev/null || true
(timeout 10 rosbag play /tmp/demo.bag >/tmp/play.log 2>&1 &)
sleep 1 && rostopic echo -n 1 /rl_demo
```

自动检查会断言回放后 `rostopic echo` 能收到 `data:` 消息，而不是只看 `rosbag --help` 是否存在。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| bag 打不开 `Error reading bag` | 录制时磁盘满/进程被杀 | 检查磁盘，重新录 |
| 回放后下游无反应 | 话题名或时钟不一致 | `--clock` + `use_sim_time` |
| 回放速度不对 | 时间戳被改写 | 保持原始时间戳，用 `--rate` |
| bag 巨大 | 录了图像/点云 | 只录必要话题，或分段 |
| 回放把车动了 | 没断开执行层 | 先切断执行或进仿真 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s1
- 来源：`C_现场踩坑`、`E_ROS与Linux命令手册`
- 外部参考：ROS Noetic `rosbag` 文档
- 产出物：一份可复盘的诊断 bag（脱敏后）

## 9. 下一节

S1-07 · TF 入门与 RViz：把「在哪」说清楚。
