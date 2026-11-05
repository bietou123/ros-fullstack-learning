# S2-06 · launch.py 与参数文件

> 验证状态：✅ 2026-11-04 在 `ros:humble-ros-base` 容器内实测（`--network host`）：`ros2 launch` 执行 `ExecuteProcess` 产生文件副作用，`ros2 param get/dump` 读取运行中节点参数均通过。

## 1. 现场类比

ROS1 的 launch 是 XML；ROS2 换成 Python 文件。表面麻烦一点，换来的是：**可以用条件、循环、环境变量、甚至读配置文件来拼启动流程**。

现场意义：不同车型、不同配置的启动差异，可以放在一个 launch 里用参数区分，而不是维护十份 xml。

## 2. 核心概念

### 2.1 最小 launch.py

```python
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    speed = LaunchConfiguration("speed")
    return LaunchDescription([
        DeclareLaunchArgument("speed", default_value="0.8"),
        Node(
            package="rl_demo",
            executable="pub",
            name="rl_pub",
            output="screen",
            parameters=[{"speed_limit": speed}, "config/params.yaml"],
        ),
    ])
```

### 2.2 参数的三层优先级（从低到高）

```
包默认值  <  yaml 文件  <  launch 内联 / 命令行传参
```

现场经常「改了 yaml 不生效」，就是被更高优先级覆盖了。

### 2.3 参数文件格式

```yaml
rl_pub:
  ros__parameters:
    speed_limit: 0.8
    rate_hz: 20
```

注意 `ros__parameters` 是**双下划线**；节点名必须与 launch 中 `name=` 一致。

### 2.4 常用动作

| 动作 | 用途 |
|---|---|
| `Node` | 起一个节点 |
| `IncludeLaunchDescription` | 复用别的 launch |
| `GroupAction` + `PushRosNamespace` | 加命名空间 |
| `TimerAction` | 延迟启动 |
| `ExecuteProcess` | 起非 ROS 程序 |

**命名空间**是多车/多机场景的关键：同一套节点用 `vehicle_a` / `vehicle_b` 两个命名空间，话题自动隔离。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

ros2 launch rl_demo demo.launch.py
ros2 launch rl_demo demo.launch.py speed:=1.2
ros2 param list /rl_pub
ros2 param get /rl_pub speed_limit
ros2 param dump /rl_pub
```

## 4. 动手实验

**目标（30 分钟）**：用 launch 起两个节点，并用参数覆盖。

1. 写 `launch/demo.launch.py`，起 `pub` 与 `echo`（或订阅节点）；
2. `ros2 launch rl_demo demo.launch.py`，确认两个节点都在；
3. 用 `speed:=1.2` 覆盖，`ros2 param get` 验证；
4. 加 `PushRosNamespace("vehicle_a")`，确认话题变成 `/vehicle_a/...`；
5. 再起一份 `vehicle_b`，验证两套话题互不干扰。

**通过判据**：能说清「yaml 里的值为什么会被 launch 覆盖」，并能用命名空间隔离两套系统。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && ros2 launch --help | head -n 3
source /opt/ros/humble/setup.bash && ros2 param --help | head -n 3
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `package not found` | 没 source install | `source install/setup.bash` |
| 参数不生效 | 优先级被覆盖 | 打印实际值，`param dump` 对比 |
| yaml 不生效 | 键写错 `ros__parameters` | 核对双下划线 |
| 节点名对不上 | launch `name=` 与 yaml 不一致 | 统一命名 |
| 两个节点抢同一话题 | 没用命名空间 | `PushRosNamespace` |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS 2 Humble Launch / Parameters 文档
- 产出物：多节点启动文件 + 两套命名空间验证

## 9. 下一节

S2-07 · ros2 bag 与诊断：ROS2 版本的现场取证。
