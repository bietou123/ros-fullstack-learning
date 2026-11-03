# S3-06 · 挖机关节链 URDF 实战

> 验证状态：✅ 2026-11-03 在本地构建的 `ros:humble-xacro` 镜像（`ros:humble-ros-base` + `ros-humble-xacro`）内实测 `check_urdf`、`xacro`、`robot_state_publisher` 均可用；RViz/joint_state_publisher_gui 图形界面未验证。文中所有尺寸为教学示例值，非任何实车参数。

## 1. 现场类比

前面几节分别学了 URDF、xacro、TF、连杆几何。这一节把它们拼成**一台能动的车**：

```
base_link → 回转 → 动臂 → 斗杆 → 铲斗
```

拼好之后，界面上的三维模型就能跟着真实编码器动——这是远控「看得见」的基础。

## 2. 核心概念

### 2.1 关节链与命名

| link | 父 joint | 类型 | 说明 |
|---|---|---|---|
| `base_link` | — | — | 车体 |
| `swing_link` | `swing_joint` | revolute（Z） | 回转 |
| `boom_link` | `boom_joint` | revolute（Y） | 动臂 |
| `arm_link` | `arm_joint` | revolute（Y） | 斗杆 |
| `bucket_link` | `bucket_joint` | revolute（Y） | 铲斗 |
| `imu_link` | `imu_joint` | fixed | 安装位姿 |

**命名要与驱动、话题、日志全线一致**：`boom_joint` 在哪都叫这个名字，别在代码里改 `boom`。

### 2.2 完整示例（xacro 片段）

```xml
<?xml version="1.0"?>
<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="rl_excavator">
  <xacro:property name="boom_len" value="4.0"/>   <!-- 示例值 -->
  <xacro:property name="arm_len" value="2.5"/>    <!-- 示例值 -->

  <link name="base_link"/>

  <joint name="swing_joint" type="revolute">
    <parent link="base_link"/>
    <child link="swing_link"/>
    <origin xyz="0 0 0.6"/>
    <axis xyz="0 0 1"/>
    <limit lower="-2.8" upper="2.8" effort="1000" velocity="0.6"/>
  </joint>
  <link name="swing_link"/>

  <joint name="boom_joint" type="revolute">
    <parent link="swing_link"/>
    <child link="boom_link"/>
    <origin xyz="0.3 0 0.2"/>
    <axis xyz="0 1 0"/>
    <limit lower="-0.5" upper="1.0" effort="2000" velocity="0.5"/>
  </joint>
  <link name="boom_link">
    <visual>
      <geometry><box size="${boom_len} 0.3 0.4"/></geometry>
      <origin xyz="${boom_len/2} 0 0"/>
    </visual>
  </link>

  <joint name="arm_joint" type="revolute">
    <parent link="boom_link"/>
    <child link="arm_link"/>
    <origin xyz="${boom_len} 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="-2.5" upper="-0.2" effort="1500" velocity="0.6"/>
  </joint>
  <link name="arm_link">
    <visual>
      <geometry><box size="${arm_len} 0.25 0.3"/></geometry>
      <origin xyz="${arm_len/2} 0 0"/>
    </visual>
  </link>

  <joint name="bucket_joint" type="revolute">
    <parent link="arm_link"/>
    <child link="bucket_link"/>
    <origin xyz="${arm_len} 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="-2.6" upper="0.4" effort="1200" velocity="0.8"/>
  </joint>
  <link name="bucket_link"/>
</robot>
```

### 2.3 三条验收标准

1. `check_urdf` 通过；
2. RViz 里拖动每个关节，**方向与实车一致**；
3. 全行程扫描，**模型与实车拍照对比无穿模**。

方向不对就改 `axis` 的符号，不要在下游代码里乘 -1——那会把错误扩散到算法层。

### 2.4 传感器框架的挂法

```xml
<joint name="imu_joint" type="fixed">
  <parent link="bucket_link"/>
  <child link="imu_link"/>
  <origin xyz="0.1 0 0.05" rpy="0 0 0"/>
</joint>
```

外参在这里先写**标称值**，标定后回填。标定值与模型不一致时，以标定值为准并更新模型。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

xacro exc.urdf.xacro > /tmp/exc.urdf
check_urdf /tmp/exc.urdf
urdf_to_graphiz /tmp/exc.urdf

ros2 run robot_state_publisher robot_state_publisher \
  --ros-args -p robot_description:="$(cat /tmp/exc.urdf)"
ros2 run joint_state_publisher_gui joint_state_publisher_gui
rviz2
```

## 4. 动手实验

**目标（45 分钟）**：完成一条五关节链并用真实数据驱动。

1. 按 2.2 搭出五个 link 的模型（尺寸用你自己的示例值）；
2. `check_urdf` 通过，`urdf_to_graphiz` 导出结构图；
3. 用 `joint_state_publisher_gui` 逐个关节扫行程，记录方向；
4. 写一个节点从「模拟编码器文件」读角度发布 `/joint_states`；
5. 在 RViz 中把 Fixed Frame 设为 `base_link`，截一张全展开图。

**通过判据**：五个关节方向全部正确，`/joint_states` 的频率稳定 ≥ 50 Hz。

## 5. 自动检查

镜像 `ros:humble-xacro`（基于 `ros:humble-ros-base` + `ros-humble-xacro`；`ros-base` 本身不含 xacro）。构建：

```bash
docker build -t ros:humble-xacro scripts/experiment-images/ros-humble-xacro
```

```bash
source /opt/ros/humble/setup.bash && command -v check_urdf
source /opt/ros/humble/setup.bash && command -v xacro
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 某个关节不动 | joint_states 名字不一致 | 对比 URDF 与驱动 |
| 模型穿模 | 视觉原点偏了 | 调 `<visual><origin>` |
| 方向相反 | axis 符号错 | 改 axis，不在代码里补偿 |
| RViz 无模型 | robot_description 未设 | 检查参数 |
| 模型跳动 | joint_states 断续 | 查采集频率与丢帧 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s3
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 产出物：可动挖机模型 + 关节方向核对表

## 9. 下一节

S4-01 · CAN 物理层与帧结构：从模型走到车上的一根线。
