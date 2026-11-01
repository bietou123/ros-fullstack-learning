# S2-02 · colcon 工作空间与包

> 验证状态：⚠ 本机未安装 ROS2，本课命令**未在本机执行**。实验使用 `ros:humble-ros-base` 容器。

## 1. 现场类比

ROS1 的 catkin 是「一个工作空间一个 make」，ROS2 的 colcon 是「一堆包并行构建，各管各的依赖」。

差别带来的现场价值：**某个包编译失败，不影响其它包继续构建**，你能先上车、后修那个坏的。

## 2. 核心概念

### 2.1 目录与产物

```
ros2_ws/
├── src/
│   └── rl_demo/
│       ├── package.xml
│       ├── setup.py
│       ├── setup.cfg
│       ├── rl_demo/__init__.py
│       └── rl_demo/pub.py
├── build/      ← 中间产物
├── install/    ← 最终产物（source install/setup.bash）
└── log/        ← colcon 日志（排错先看 latest_build）
```

### 2.2 建包与构建

```bash
ros2 pkg create --build-type ament_python rl_demo --dependencies rclpy std_msgs
colcon build --packages-select rl_demo
source install/setup.bash
ros2 run rl_demo pub
```

`--packages-select` 只编一个包，**大工作空间里能省掉大半时间**。

### 2.3 catkin 与 colcon 对照

| 事项 | catkin | colcon |
|---|---|---|
| 构建命令 | `catkin_make` | `colcon build` |
| 激活脚本 | `devel/setup.bash` | `install/setup.bash` |
| 单包构建 | 需切目录/参数 | `--packages-select` |
| 类型 | rospy / roscpp | ament_python / ament_cmake |

### 2.4 构建失败的定位

```bash
colcon build --packages-select rl_demo --event-handlers console_direct+
```

`console_direct+` 把每个包的输出直接打出来；不带这个参数时，错误藏在 `log/latest_build/<包名>/stderr.log` 里。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash
mkdir -p ~/ros2_ws/src && cd ~/ros2_ws
ros2 pkg create --build-type ament_python rl_demo --dependencies rclpy std_msgs
colcon build --packages-select rl_demo
source install/setup.bash
ros2 pkg prefix rl_demo
ros2 run rl_demo pub
```

## 4. 动手实验

**目标（35 分钟）**：建包 → 写节点 → 构建 → 运行。

1. 按上面命令建 `rl_demo`；
2. 在 `rl_demo/rl_demo/pub.py` 写一个 5 Hz 发布者，`setup.py` 的 `console_scripts` 里注册 `pub`；
3. `colcon build --packages-select rl_demo`；
4. `source install/setup.bash && ros2 run rl_demo pub`；
5. 另开终端 `ros2 topic echo /rl_chat` 验证。

**通过判据**：能说出 `build`/`install`/`log` 三个目录各自的用途，并能解释为什么必须 `source install/setup.bash`。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && command -v colcon
source /opt/ros/humble/setup.bash && ros2 pkg create --help | head -n 2
```

构建过程需写盘，容器为单次执行，产物不会保留到下一个命令。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `colcon: command not found` | 没装/没 source | `sudo apt install python3-colcon-common-extensions` |
| `ros2 run` 找不到可执行 | 没注册 console_scripts / 没 source | 检查 `setup.py`，重新 source |
| 构建卡住 | 依赖缺失在循环重试 | 看 `log/latest_build/*/stderr.log` |
| 改了代码不生效 | 只改源码没重编 | `colcon build --packages-select rl_demo` |
| 多个工作空间覆盖 | source 顺序 | 后 source 优先，检查 `AMENT_PREFIX_PATH` |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS 2 Humble（Creating a workspace / ament_python）
- 产出物：可运行的 `rl_demo` ament_python 包

## 9. 下一节

S2-03 · rclpy 节点与 QoS：为什么 ROS2「消息会丢」。
