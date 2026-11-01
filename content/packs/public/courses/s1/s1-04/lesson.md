# S1-04 · topic、消息与 rostopic 诊断

> 验证状态：⚠ 本机未安装 ROS，本课命令**未在本机执行**。容器实验见第 5 节。

## 1. 现场类比

「车端收不到指令」时，90% 的人第一反应是看日志。更快的顺序是：

```
有没有话题 → 有没有发布者 → 频率对不对 → 内容对不对 → 时间戳对不对
```

`rostopic` 五条命令正好覆盖这五步。**先量化，再猜原因**。

## 2. 核心概念

### 2.1 诊断五件套

| 命令 | 回答的问题 | 现场用法 |
|---|---|---|
| `rostopic list` | 有哪些话题 | 确认名字存在 |
| `rostopic info /x` | 谁发、谁收、什么类型 | 判断链路是否接上 |
| `rostopic hz /x` | 多久来一帧 | 判断断流/过载 |
| `rostopic echo /x` | 内容是什么 | 判断数值与单位 |
| `rostopic bw /x` | 占多少带宽 | 判断是否把总线打满 |

对应消息侧：`rosmsg show 包/类型`、`rosmsg list`。

### 2.2 读 `rostopic info` 的三件事

```
Type: std_msgs/String
Publishers:
 * /rl_pub (http://host:端口/)
Subscribers:
 * /rl_sub
```

- 类型不一致 → 即使名字对也收不到；
- 0 个 Publisher → 上游没起来；
- 多个 Publisher → 可能两个节点抢发同一话题，**现场最隐蔽的故障之一**。

### 2.3 频率与时间戳

`rostopic hz` 给的是**到达间隔**，不是发布间隔。把两者混为一谈会得出错误结论：

- 发布 50 Hz、到达 20 Hz → 链路或订阅端在处理上丢帧；
- 发布 20 Hz、到达 20 Hz 但 `header.stamp` 停滞 → 上游复用了旧消息。

**判断断流看 `hz` 是否归零，判断数据是否新鲜看 `header.stamp`。**

### 2.4 常见消息字段

| 字段 | 意义 | 坑 |
|---|---|---|
| `header.stamp` | 时间戳 | 用 `rospy.Time.now()`，不要用 `time.time()` 直接塞 |
| `header.frame_id` | 坐标框架 | TF 找不到框架多半错在这 |
| `data` | 载荷 | 注意单位（m / mm、rad / deg） |

## 3. 可复制命令 / 代码

```bash
source /opt/ros/noetic/setup.bash
rostopic list
rostopic info /rl_chat
rostopic echo -n 3 /rl_chat
rostopic hz /rl_chat
rostopic bw /rl_chat
rosmsg show std_msgs/String
```

## 4. 动手实验

**目标（30 分钟）**：用频率与时间戳给出一个有证据的结论。

1. 启动 `roscore`，用 `rostopic pub -r 20 /rl_demo std_msgs/String "data: x"` 造流量；
2. 测 `rostopic hz /rl_demo`，记录实测频率；
3. 同时开 `rostopic echo /rl_demo`，观察是否丢帧；
4. 把发布频率改成 200 Hz，再测带宽 `rostopic bw`；
5. 写结论：「频率 = __ Hz，带宽 = __ KB/s，丢帧现象 = __」。

**通过判据**：结论里每个数字都来自命令输出，不写「大概很正常」。

## 5. 自动检查

镜像 `ros:noetic-ros-base`：

```bash
source /opt/ros/noetic/setup.bash && which rostopic rosmsg
source /opt/ros/noetic/setup.bash && rosmsg show std_msgs/String | head -n 3
```

预期 `rosmsg show` 输出 `string data`。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `rostopic list` 有话题但 echo 无输出 | 发布者无数据 / 断流 | `rostopic hz` 定位 |
| `hz` 显示 `no new messages` | 上游没发 | `rostopic info` 看 Publisher 数 |
| 类型不匹配报错 | 同名不同 `_type` | `rosmsg show` 比对 |
| 数据对但车不动 | 单位/方向/限幅 | 回看 S0-07 分层表，往执行层走 |
| 带宽打满 | 高频大消息 | 降频、压缩、拆分话题 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s1
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 外部参考：ROS Noetic `rostopic` / `rosmsg` 工具
- 产出物：一次 topic 诊断记录（频率、带宽、结论）

## 9. 下一节

S1-05 · service、param、launch：把「能跑」变成「能配置地跑」。
