# S3-01 · URDF 基础：link 与 joint

> 验证状态：⚠ 本机未安装 ROS，本课命令**未在本机执行**。URDF 校验使用 `ros:humble-ros-base` 容器（含 urdfdom 工具）。

## 1. 现场类比

要给远控车做三维监视，第一步不是找模型文件，而是回答：**车由哪几块刚体组成、块与块之间怎么连、转轴在哪、转多少度**。

URDF 就是把这四个问题写成一份可被 ROS 读懂的说明书。写错一个轴，模型就会往反方向动——而现场往往先怀疑数据。

## 2. 核心概念

### 2.1 两个元素

| 元素 | 含义 | 关键属性 |
|---|---|---|
| `<link>` | 刚体（不可变形的零件） | 名字、视觉、碰撞、质量惯性 |
| `<joint>` | 两个 link 之间的连接 | 父子关系、类型、原点、轴、限位 |

**URDF 只能表示树**：每个 link 最多一个父 joint。闭环机构（四连杆）不能直接表达——这是 S3-05 的主题。

### 2.2 joint 的六种类型

| 类型 | 自由度 | 典型用途 |
|---|---|---|
| fixed | 0 | 传感器安装、结构件 |
| revolute | 1（有限位） | 动臂、斗杆、铲斗 |
| continuous | 1（无限位） | 轮子 |
| prismatic | 1（平移） | 液压缸、滑轨 |
| floating | 6 | 极少用 |
| planar | 3 | 极少用 |

### 2.3 最小可校验模型

```xml
<?xml version="1.0"?>
<robot name="rl_demo">
  <link name="base_link"/>

  <link name="arm_link">
    <visual>
      <geometry><box size="2.0 0.2 0.2"/></geometry>
      <origin xyz="1.0 0 0"/>
      <material name="orange"><color rgba="1 0.5 0 1"/></material>
    </visual>
  </link>

  <joint name="arm_joint" type="revolute">
    <parent link="base_link"/>
    <child link="arm_link"/>
    <origin xyz="0 0 0.5" rpy="0 0 0"/>
    <axis xyz="0 1 0"/>
    <limit lower="-1.57" upper="1.57" effort="100" velocity="1.0"/>
  </joint>
</robot>
```

### 2.4 三个最容易错的地方

| 错误 | 现象 | 检查 |
|---|---|---|
| `<origin>` 与 `<visual>` 顺序写反 | 模型位置偏 | `check_urdf` + RViz |
| `axis` 方向错 | 正转变成反转 | 用右手定则核对 |
| 缺 `<limit>` | `check_urdf` 报错或关节不可动 | 所有 revolute/prismatic 必须有限位 |

**`<origin>` 是相对父 link 的位置**，不是世界坐标。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

check_urdf /tmp/demo.urdf
urdf_to_graphiz /tmp/demo.urdf        # 需 graphviz，生成结构图
ros2 run robot_state_publisher robot_state_publisher /tmp/demo.urdf
```

## 4. 动手实验

**目标（30 分钟）**：搭一个两连杆模型并在 RViz 里转动。

1. 用 2.3 的模板扩展到两节（动臂 + 斗杆）；
2. `check_urdf` 确认无语法错误；
3. 用 `joint_state_publisher_gui` 拖动关节，观察模型；
4. 故意把 `axis` 改成 `0 0 1`，观察运动方向变化；
5. 故意删掉 `limit`，记录 `check_urdf` 报错原文。

**通过判据**：能解释「同一个 joint，改 axis 后运动方向为什么变」，并能说出 URDF 为什么不能表达闭环。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && command -v check_urdf
source /opt/ros/humble/setup.bash && rospack find urdf 2>/dev/null || ros2 pkg list | grep -c urdf
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `check_urdf` 报 XML 错误 | 标签未闭合/拼写错 | 看报错行号，逐层闭合 |
| 模型全在原点 | origin 没写 | 补 `xyz` |
| 关节不动 | 没发 joint_states | 用 `joint_state_publisher` |
| 模型翻转 | rpy 顺序或轴错 | 按 roll-pitch-yaw 核对 |
| RViz 报 No transform | 固定坐标系没设 | 设 Fixed Frame 为 `base_link` |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s3
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS 2 URDF 教程
- 产出物：两连杆 URDF + `check_urdf` 通过记录

## 9. 下一节

S3-02 · xacro 参数化：一个模型，多个机型。
