# S1-05 · service、param、launch

> 验证状态：✅ 2026-11-04 在 `ros:noetic-ros-base` 容器内实测（`--network host`）：`rosparam set/get/list` 往返、`rosservice list` 出现 `get_loggers` 均通过。

## 1. 现场类比

topic 是「一直播报」，适合连续量（速度、角度）。但「切换工作模式」「请求标定」这类**一次性、要等结果**的动作，用 topic 会很难确认到底成没成功——这就是 service。

而「同一个程序，A 车速度上限 1.2、B 车 0.8」，不该改代码，该改参数——这就是 param。

最后，现场一次要起十几个节点，不能靠开十几个终端——这就是 launch。

## 2. 核心概念

### 2.1 三种通信方式对比

| 方式 | 方向 | 是否等待 | 典型用途 |
|---|---|---|---|
| topic | 单向广播 | 不等 | 手柄、状态、指令流 |
| service | 请求/响应 | 等返回 | 切模式、标定、复位 |
| action | 长任务+反馈 | 可取消 | 导航到点、长行程动作 |

**service 不适合高频**：每次调用都要建连接、等返回，50 Hz 的控制量用 service 会拖慢整条链路。

### 2.2 param 的两层

```bash
rosparam set /rl_speed_limit 1.2      # 运行时改，重启即丢
rosparam get /rl_speed_limit
rosparam list | head
rosparam dump /tmp/params.yaml        # 落盘备份
rosparam load /tmp/params.yaml        # 恢复
```

参数服务器在 master 里，**master 一挂参数全没**。重要参数必须落到 yaml 文件并进版本管理（配合 S0-05 的 Git 纪律）。

### 2.3 launch 文件最小模板

```xml
<launch>
  <arg name="speed" default="0.8"/>
  <param name="rl_speed_limit" value="$(arg speed)"/>

  <node pkg="rl_demo" type="rl_pub.py" name="rl_pub" output="screen">
    <param name="rate_hz" value="20"/>
  </node>

  <node pkg="rl_demo" type="rl_sub.py" name="rl_sub" output="screen"/>
</launch>
```

```bash
roslaunch rl_demo demo.launch speed:=1.2
```

`output="screen"` 让节点日志打到当前终端；**不加这两字，`roslaunch` 默认把日志藏起来**，现场排查时最容易被坑。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/noetic/setup.bash
roscore
rosparam set /rl_speed_limit 1.2
rosparam get /rl_speed_limit
rosparam list | grep rl_
rosservice list | head
roslaunch --help | head -n 3
```

## 4. 动手实验

**目标（40 分钟）**：把参数写进 launch，并从外部覆盖。

1. 在 `rl_demo` 下建 `launch/demo.launch`（用 2.3 模板）；
2. `roslaunch rl_demo demo.launch`，另开终端 `rosparam get /rl_speed_limit`，应为 0.8；
3. 停掉，改用 `roslaunch rl_demo demo.launch speed:=1.2` 再查，应为 1.2；
4. `rosparam dump` 导出，比较两次差异；
5. 新增一个 service 节点（`rospy.Service`），用 `rosservice call` 调一次并检查返回。

**通过判据**：能解释「arg、param、节点私有 param」三者的区别，并说明为什么 `rosparam set` 的值重启就没了。

## 5. 自动检查

镜像 `ros:noetic-ros-base`：

```bash
source /opt/ros/noetic/setup.bash && which roslaunch rosservice rosparam
source /opt/ros/noetic/setup.bash && rosparam --help | head -n 2
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `roslaunch` 起不来 | launch 路径不在包内 | 必须放 `<pkg>/launch/*.launch` |
| 参数读不到 | 命名空间/私有参数 | 区分 `/x`、`x`、`~x` |
| 节点日志看不到 | 没开 `output="screen"` | 加上或去 `~/.ros/log` 找 |
| 同名节点冲突 | launch 与手工启动重名 | 统一用 launch 起 |
| service 调用超时 | 服务端没起或阻塞回调 | `rosservice list` 确认存在 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s1
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS Noetic launch / rosservice / rosparam 文档
- 产出物：可参数化的 `demo.launch` 与两次参数对比

## 9. 下一节

S1-06 · rosbag 录制与回放：把一次现场问题完整带走。
