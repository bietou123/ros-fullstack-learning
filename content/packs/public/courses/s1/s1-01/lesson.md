# S1-01 · ROS1 世界观：master / node / topic

> 验证状态：✅ 2026-11-04 在 `ros:noetic-ros-base` 容器内实测（`--network host`）：`rosversion -d`、`rospack find roscpp`、启动 `roscore` 后 `rosnode list` 出现 `/rosout`、`rostopic list` 均通过。

## 1. 现场类比

远控车上，手柄输入、姿态解算、CAN 下发是三拨人写的三份程序。传统做法是「A 直接调 B 的函数」，一改接口全员重编；ROS 的做法是让大家**都往公告栏上贴/看纸条**：

- `master` = 公告栏管理员（记录谁在贴、谁在看）；
- `node` = 一个干活的进程；
- `topic` = 一根有名字的公告线，贴的人不用知道谁在看。

**松耦合的代价**是「谁在贴、贴在哪个名字上」必须约定清楚——这也是现场 80% 的 ROS 故障来源。

## 2. 核心概念

### 2.1 五个名词

| 名词 | 含义 | 一句话记法 |
|---|---|---|
| master | 名字注册与查询中心，`roscore` 启动 | 电话总机，不传数据 |
| node | 一个 ROS 进程，有唯一名字 | 一个工位 |
| topic | 有名字的异步消息通道 | 广播频道 |
| message | topic 上传输的结构化数据 | 频道的语言 |
| publisher / subscriber | 往 topic 写 / 从 topic 读 | 说话的人 / 听的人 |

**关键事实**：master 只做「谁在哪」的登记，数据是节点之间**直连**传输的。所以 master 挂了，已在通信的节点还能继续跑，但新节点起不来。

### 2.2 一张最小节点图

```
[手柄节点] --/joy--> [控制节点] --/cmd--> [CAN 桥节点] --> 车辆
                          ↑
                     [/status 反馈]
```

`rqt_graph` 画的就是这张图；**能画出来，说明名字与连接是对的**。

### 2.3 ROS1 与 ROS2 的对应

| 概念 | ROS1（Noetic） | ROS2（Humble） |
|---|---|---|
| 启动核心 | `roscore` | 无中心，DDS 自动发现 |
| 构建 | catkin / `catkin_make` | colcon |
| 运行节点 | `rosrun 包 节点` | `ros2 run 包 节点` |
| 看话题 | `rostopic list` | `ros2 topic list` |

本阶段先学 ROS1，原因是现场存量车端大量是 Noetic；迁移点集中在 S4。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/noetic/setup.bash

roscore                      # 终端 1：启动 master
rosnode list                 # 终端 2：有哪些节点
rostopic list                # 有哪些话题
rostopic info /rosout        # 某个话题的类型与收发者
rqt_graph                    # 图形化节点图（需桌面环境）
```

## 4. 动手实验

**目标（30 分钟）**：画出一张真实的节点图。

1. 启动容器：`docker run --rm -it ros:noetic-ros-base bash`；
2. 容器内 `source /opt/ros/noetic/setup.bash`；
3. 终端 1 `roscore`，终端 2 `rostopic pub -r 5 /rl_demo std_msgs/String "data: hello"`；
4. 终端 3 执行 `rosnode list`、`rostopic list`、`rostopic info /rl_demo`；
5. 把三份输出画成节点图（哪怕只是纸上的方框+箭头）。

**通过判据**：能说出 `/rl_demo` 上**有几个发布者、几个订阅者**，以及 `rosnode list` 里多出来的 `/rosout` 是谁。

## 5. 自动检查

「实验」页签使用镜像 `ros:noetic-ros-base` 执行：

```bash
source /opt/ros/noetic/setup.bash && rosversion -d
source /opt/ros/noetic/setup.bash && rospack find std_msgs
```

预期输出 `noetic` 与 `std_msgs` 的安装路径。容器是 `--rm` 的，**上一个命令产生的文件不会留到下一个命令**，所以检查只验证工具链而不验证产物。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `Couldn't find an AF_INET address for [...]` | ROS_MASTER_URI 指向错 | `echo $ROS_MASTER_URI`，确认 IP 可达 |
| 节点在但收不到数据 | 话题名不一致（`/a` 与 `a`） | `rostopic list` 比对全名 |
| `rosnode list` 报错连不上 | master 没起 | `roscore` 或检查端口 11311 |
| 多机通信时断时续 | 两台机器时间不同步 | 统一 NTP，检查 `date` |
| 同名节点互相顶掉 | 节点名冲突 | 用 `<node name="...">` 改名或加命名空间 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s1
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS Noetic 官方文档（Concepts → Nodes / Topics）
- 产出物：节点图（话题名、发布者、订阅者）

## 9. 下一节

S1-02 · 工作空间与 catkin 包：把「一个脚本」变成「可被 rosrun 的包」。
