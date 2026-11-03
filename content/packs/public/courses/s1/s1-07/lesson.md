# S1-07 · TF 入门与 RViz

> 验证状态：✅ 2026-11-03 在 `ros:noetic-perception` 容器（WSL Ubuntu 24.04，headless）实测 `static_transform_publisher` 发布、`tf_echo` 查询与包检查均通过；RViz 图形界面未验证。

## 1. 现场类比

挖掘机动臂角度传感器装在**关节**上，但你要知道的是**铲斗齿尖在世界坐标的哪里**。中间隔着一串坐标系：底盘 → 回转 → 动臂 → 斗杆 → 铲斗 → 齿尖。

TF 就是这串「父子关系 + 变换」的登记表。**链路缺一环，任何跨坐标系的换算都会失败**——现象往往是「点云飘了」「模型位置不对」，而不是报错。

## 2. 核心概念

### 2.1 一棵 TF 树

```
world
└── base_link            （车体）
    ├── cabin_link
    ├── boom_base        （动臂铰点）
    │   └── boom_link
    │       └── arm_link
    │           └── bucket_link
    └── sensor_imu
```

每个箭头是一次 `TransformStamped`：父子名、平移（xyz）、旋转（四元数）、时间戳。

### 2.2 三条命令

| 命令 | 作用 | 现场用法 |
|---|---|---|
| `rosrun tf tf_echo A B` | 实时打印 A→B 变换 | 验证链路与数值 |
| `rosrun tf view_frames` | 导出整棵树（pdf） | 找断链 |
| `rosrun rviz rviz` | 可视化 | 看模型、点云、TF 轴 |

### 2.3 两个高频坑

**坑一：时间戳。** TF 查询默认用「最新可用时间」，消息时间戳太旧会被判为外推（`LookupException` / `ExtrapolationException`）。**先查时钟源，再查算法。**

**坑二：框架名拼写。** `base_link` 与 `base_link `（多空格）、`laser` 与 `laser_link` 不匹配，RViz 会整片报红但节点本身不报错。

### 2.4 静态变换与动态变换

- 传感器安装位置固定 → `static_transform_publisher`（发一次，永久有效）；
- 关节角度实时变化 → 由 joint_state 驱动，周期发布。

**把本来固定的装成动态**（或反之），是现场「模型抖动」的常见根因。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/noetic/setup.bash

# 静态发一条：base_link 原点向上 1m 是 boom_base（示例值，非实车）
rosrun tf static_transform_publisher 0 0 1 0 0 0 base_link boom_base 100

# 查询这条变换
rosrun tf tf_echo base_link boom_base

# 导出整棵树
rosrun tf view_frames
```

## 4. 动手实验

**目标（30 分钟）**：人造三节 TF 链，并在 RViz 里看到。

1. 用三个 `static_transform_publisher` 串起 `base_link → boom_base → boom_link → bucket_link`；
2. `tf_echo base_link bucket_link`，确认能算出复合变换；
3. `view_frames` 导出 pdf，检查是否有断链；
4. 在 RViz 里加 TF 显示，把 Fixed Frame 设为 `base_link`，观察三个轴是否出现在预期位置；
5. 故意改错一个父节点名，记录报错原文，再改回来。

**通过判据**：能同时说明「TF 树缺环」和「TF 时间戳过期」两种失败各自的现象差异。

## 5. 自动检查

镜像 `ros:noetic-perception`（`ros-base` 不含 tf / tf2_ros）：

```bash
source /opt/ros/noetic/setup.bash && rospack find tf
source /opt/ros/noetic/setup.bash && rospack find tf2_ros
```

注意该镜像不含 RViz；需要图形化请在本机安装 `ros-noetic-rviz` 或使用自行构建的 desktop 镜像。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `LookupException: Frame [x] does not exist` | 框架名不一致/未发布 | `view_frames` 看树 |
| `Extrapolation into the future` | 时间戳超前或时钟不同步 | 统一时钟源，检查 `use_sim_time` |
| RViz 整屏红字 | Fixed Frame 不对 | 选一个真实存在的框架 |
| 模型抖动 | 静态变换发成了周期变化 | 固定件用 `static_transform_publisher` |
| 回放 bag 后 TF 断 | bag 里没录 `/tf` | 录 bag 时带上 `/tf` |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s1
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 外部参考：ROS Noetic tf / rviz 文档
- 产出物：一张 `view_frames` 导出的 TF 树截图

## 9. 下一节

S2-01 · 消息定义与自定义 msg：为业务定义自己的语言。
