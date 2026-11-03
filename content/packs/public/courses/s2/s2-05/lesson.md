# S2-05 · lifecycle 与 composition

> 验证状态：✅ 2026-11-03 在 `ros:humble-ros-base` 容器内实测 `ros2 lifecycle` / `ros2 component` 子命令与相关包存在性检查均通过。受管节点运行与状态切换为演示流程，未在该镜像内启动实际节点。

## 1. 现场类比

ROS1 节点只有「起」和「死」。上车时十个节点同时起，谁先谁后全靠 `sleep`——偶尔能用，偶尔车一通电就报错。

lifecycle 把节点变成**像设备一样有开关**：未配置 → 已配置 → 激活（才开始干活）→ 停用 → 销毁。现场可以「所有节点先配置好，再统一激活」。

composition 解决另一个问题：十个节点十个进程，内存翻倍、进程间通信开销大。把多个节点装进**一个进程**里跑。

## 2. 核心概念

### 2.1 四个主状态

| 状态 | 含义 | 能做什么 |
|---|---|---|
| unconfigured | 已加载未配置 | 可 configure |
| inactive | 已配置未激活 | 可 activate |
| active | 正在工作 | 可 deactivate |
| finalized | 已销毁 | 不能再启动 |

**关键：在 `inactive` 时订阅/发布还不会真正工作**，这是「节点起来了但没数据」的常见原因。

### 2.2 lifecycle 命令

```bash
ros2 lifecycle list /rl_node          # 可用转换
ros2 lifecycle get /rl_node           # 当前状态
ros2 lifecycle set /rl_node configure
ros2 lifecycle set /rl_node activate
```

### 2.3 composition 两种形态

| 形态 | 启动方式 | 适用 |
|---|---|---|
| 静态组合 | launch 里 `ComposableNodeContainer` | 现场固定拓扑 |
| 动态加载 | `ros2 component load /容器 包 插件` | 调试、热插拔 |

```bash
ros2 component list
ros2 component load /rl_container rl_demo rl_demo::RlNode
ros2 component unload /rl_container <id>
```

### 2.4 什么时候值得用

- 节点多、内存紧（工控机 4G 内存很常见）→ composition；
- 启停顺序有依赖（先标定后控制）→ lifecycle；
- **只有一个节点** → 两者都不要上，复杂度不划算。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

ros2 lifecycle --help | head -n 5
ros2 component --help | head -n 5
ros2 pkg list | grep -E 'lifecycle|components' | head
ros2 run rclcpp_components component_container    # 需要该包已安装
ros2 component list
```

## 4. 动手实验

**目标（35 分钟）**：把一个普通节点改成受管节点，并观察状态机。

1. 用 `rclpy.lifecycle.LifecycleNode` 改 S2-03 的发布者；
2. 在 `on_configure` 里创建 publisher，在 `on_activate` 里开始 timer；
3. 启动后用 `ros2 lifecycle get` 查看状态，依次 configure / activate；
4. 每个状态变化时用 `ros2 topic echo` 验证是否真的开始/停止发布；
5. 画一张你自己的状态转换图。

**通过判据**：能说出「为什么在 unconfigured 状态下不会有数据」，并解释 composition 在什么条件下才值得用。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && ros2 lifecycle set --help | grep -q transition
source /opt/ros/humble/setup.bash && ros2 component --help | grep -q load
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 节点在但无数据 | 停在 inactive | `lifecycle set ... activate` |
| `lifecycle set` 报错 | 当前状态不支持该转换 | `lifecycle list` 看允许的转换 |
| composition 加载失败 | 插件名不对 | `ros2 component types` 查插件 |
| 容器内节点崩溃拖垮全部 | 同进程共享故障域 | 关键节点独立进程 |
| 内存没降 | 本来就是单节点 | 不必用 composition |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS 2 Humble Managed nodes / Composition 文档
- 产出物：受管节点 + 状态转换图

## 9. 下一节

S2-06 · launch.py 与参数文件：把一堆命令变成一次启动。
