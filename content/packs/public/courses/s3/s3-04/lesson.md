# S3-04 · RViz 与 robot_state_publisher

> 验证状态：⚠ 本机未安装 ROS，本课命令**未在本机执行**；RViz 需图形界面，容器内仅验证工具链。

## 1. 现场类比

URDF 是「车长什么样」，joint_states 是「现在每个关节在哪」，robot_state_publisher 负责把两者算成 TF。

链路断一环，RViz 就只剩一堆散落零件。**监视界面能不能用，取决于这条链是否完整**：

```
URDF → robot_state_publisher ← /joint_states ← 编码器驱动
                    ↓
                   /tf → RViz
```

## 2. 核心概念

### 2.1 三个节点的分工

| 组件 | 输入 | 输出 |
|---|---|---|
| `robot_state_publisher` | URDF + `/joint_states` | `/tf`、`/tf_static` |
| `joint_state_publisher` | 无（手工/GUI） | `/joint_states` |
| RViz | `/tf` + 模型话题 | 画面 |

**现场必须用真实 `/joint_states`**，不能留着手工滑条——那只是调试工具。

### 2.2 `/joint_states` 的最小内容

```
name: ["boom_joint", "arm_joint", "bucket_joint"]
position: [0.12, -0.45, 0.80]     # 弧度
velocity: [...]
effort: [...]
```

单位是**弧度**。编码器读出来是度、是脉冲、还是原始电压，必须在上游换算好。

### 2.3 RViz 的三个必设项

1. **Fixed Frame**：选一个真实存在的框架（通常 `base_link` 或 `world`）；
2. **RobotModel**：Topic 设为 `robot_description`；
3. **TF**：可打开显示所有坐标系，排查用。

### 2.4 关节名必须一致

URDF 里叫 `boom_joint`，`joint_states` 里叫 `boom` → robot_state_publisher 会**静默忽略**这个关节，模型部分不动。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

# 用参数方式加载 URDF（推荐）
ros2 run robot_state_publisher robot_state_publisher \
  --ros-args -p robot_description:="$(xacro model.xacro)"

ros2 topic echo /joint_states --once
ros2 run tf2_tools view_frames
rviz2
```

## 4. 动手实验

**目标（35 分钟）**：让 S3-01 的模型动起来。

1. 启动 `robot_state_publisher` 加载模型；
2. 用 `joint_state_publisher_gui` 推关节，确认模型联动；
3. 自己写一个节点按正弦规律发布 `/joint_states`（1 Hz）；
4. 把其中一个关节名改错，记录 RViz 现象；
5. 在 RViz 里打开 TF 显示，截图保存。

**通过判据**：能指出「模型不动」时该查 URDF 名、还是 joint_states 名、还是 TF 树。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && ros2 pkg list | grep -c robot_state_publisher
source /opt/ros/humble/setup.bash && ros2 pkg list | grep -c joint_state_publisher
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 模型显示不出来 | `robot_description` 未设置 | 检查参数名与内容 |
| 部分关节不动 | 关节名不匹配 | 对比 URDF 与 joint_states |
| 整个模型乱飞 | Fixed Frame 错 | 改 Fixed Frame |
| 有模型没 TF | robot_state_publisher 未运行 | 启动节点 |
| 模型抖动 | joint_states 频率过低 | 提高到 ≥ 控制频率 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s3
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 外部参考：ROS 2 robot_state_publisher / RViz 文档
- 产出物：RViz 联动截图 + 关节名对照表

## 9. 下一节

S3-05 · 挖掘机四连杆几何建模：为什么 URDF 表达不了它。
