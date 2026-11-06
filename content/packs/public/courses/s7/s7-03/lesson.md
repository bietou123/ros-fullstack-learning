# S7-03 · Nav2 架构

> 验证状态：✅ 本课行为树状态聚合命令已在本机 Linux 实测；✅ 2026-11-06 在 `ros:humble-nav2` 容器内启动完整 Nav2 栈，9 个生命周期节点全部 `active`、12 个动作服务器可用，`map→base_link` TF 正常，并完成一次成功导航与一次地图外目标的失败/恢复实测；⚠ 真实底盘、真实传感器与现场参数仍未实测。

## 1. 现场类比

规划器算出路线，控制器却原地打转。查了半天发现：规划用的是 5 秒前的地图，控制用的是刚更新的障碍层。

**Nav2 不是「一个规划器」，是多个节点分工协作。** 不知道谁负责什么，排障就只能猜。

## 2. 核心概念

### 2.1 主要节点

| 节点 | 职责 | 输入 → 输出 |
|---|---|---|
| `bt_navigator` | 执行行为树，编排整个导航流程 | 目标 → 各服务器调用 |
| `planner_server` | 全局路径规划 | 起点/终点 + 全局代价地图 → 路径 |
| `controller_server` | 局部路径跟踪 | 路径 + 局部代价地图 → 速度指令 |
| `behavior_server` | 恢复行为（清图、转圈、后退） | 触发 → 恢复动作 |
| `smoother_server` | 路径平滑 | 原始路径 → 平滑路径 |
| `waypoint_follower` | 多点巡航 | 航点列表 → 依次执行 |
| `velocity_smoother` | 速度限幅/平滑 | 速度 → 受限速度 |

### 2.2 坐标系链

```
map ──(定位)──▶ odom ──(里程计)──▶ base_link
```

- `map → odom`：定位节点发布，会跳变（重定位时）；
- `odom → base_link`：里程计发布，连续但会漂；
- 规划用 `map`，控制一般也用 `map` 或 `odom`，**不要混用坐标系**。

### 2.3 行为树（BT）

Nav2 用行为树而不是写死流程：

```
Sequence
 ├─ ComputePathToPose（全局规划）
 ├─ FollowPath（控制）
 └─ Fallback（失败恢复）
      ├─ 清除代价地图
      ├─ 原地旋转
      └─ 后退
```

- **Sequence**：全部成功才成功；
- **Fallback**：任意一个成功即成功，用于恢复；
- 节点返回 `SUCCESS / FAILURE / RUNNING`。

**看懂行为树，才知道「卡住时系统在试什么」。**

### 2.4 生命周期

Nav2 节点是 lifecycle 节点：`unconfigured → inactive → active`。

好处：可以「配好了但不激活」，参数错误在 configure 阶段暴露，避免半启动状态。排障时先看生命周期状态，再看话题。

## 3. 可复制命令 / 代码

```bash
# 行为树状态聚合：Sequence 有一个失败即失败；Fallback 有一个成功即成功
python3 -c "seq=lambda x:'SUCCESS' if all(v=='SUCCESS' for v in x) else 'FAILURE'; fall=lambda x:'SUCCESS' if any(v=='SUCCESS' for v in x) else 'FAILURE'; print('seq=%s fall=%s'%(seq(['SUCCESS','FAILURE']),fall(['FAILURE','SUCCESS'])))"
```

预期：`seq=FAILURE fall=SUCCESS`。这解释了为什么控制器失败后，恢复行为仍可能让整条导航继续。

**可复现的 Nav2 全栈实测**：在 `ros:humble` 上装 `ros-humble-nav2-bringup`（本机为 1.1.20，已含 map_server/amcl/nav2 全套），配一个发布 `/scan`、`/odom`、`map→odom→base_link` TF 并订阅 `/cmd_vel` 的合成差速底盘中转节点，用 8×6 m 房间栅格图启动：

```bash
ros2 launch nav2_bringup bringup_launch.py use_sim_time:=false \
  map:=/map/rl_map.yaml params_file:=/out/nav2_params.yaml \
  autostart:=true use_composition:=False
```

从 `nav2_bringup` 默认参数派生时，必须把 `amcl.base_frame_id` 改成与实际 TF 一致的 `base_link`（默认是 `base_footprint`），否则 AMCL 只报 `Couldn't transform from laser to base_footprint`，`map→odom` 永远不会发布，规划器和控制器会一直等 TF。启动后实测：9 个生命周期节点（`map_server`、`amcl`、`bt_navigator`、`planner_server`、`controller_server`、`behavior_server`、`smoother_server`、`waypoint_follower`、`velocity_smoother`）全部 `active [3]`；动作服务器 12 个，含 `navigate_to_pose`、`compute_path_to_pose`、`follow_path`、`spin`、`backup`、`wait`、`smooth_path`；`map→base_link` 读数 `(1.200, 0.000)`、yaw 90°。发目标 `(1.0, -1.0)`：8.71 s 后 `Goal finished with status: SUCCEEDED`，`number_of_recoveries: 0`，剩余距离 0.221 m（默认 `xy_goal_tolerance` 0.25 m）。再发一个地图外目标 `(6.0, 0.0)`：规划器立即报 `worldToMap failed: mx,my: 204,64, size_x,size_y: 168,128` 与 `The goal sent to the planner is off the global costmap`，行为树请求清除全局/局部代价地图，并因动作确认超时以 `Goal failed` / `ABORTED` 结束（`number_of_recoveries: 5`），底盘原地未动。

三个实测踩坑：
- 命令行轮询 `ros2 lifecycle get` 可能长时间不返回。把等待循环里的查询包在 `timeout 5` 内，否则整套 Nav2 已经激活，脚本却卡死在下一次查询上。
- `bt_navigator` 的 `default_server_timeout` 默认只有 20 ms。CPU 被占满的容器里，清除局部代价地图、spin/wait/backup 的动作确认会超时（日志为 `Timed out while waiting for action server to acknowledge goal request`），恢复行为还没跑完导航就以 ABORTED 结束；资源紧张的设备上要适当放大。
- 目标在地图外时属于「规划阶段必失败」，不要把它当成行为树恢复失败的证据；恢复行为只在路径可算、执行阶段出错时才真正展开。

## 4. 动手实验

**目标（40 分钟）**：画出你的 Nav2 节点与话题关系图，并解释一次失败。

1. 列出启动的 Nav2 节点及其生命周期状态；
2. 画出 `map → odom → base_link` 的 TF 链，标明谁发布；
3. 画出全局/局部代价地图分别被谁使用；
4. 人为设置一个不可达目标，观察行为树如何进入恢复；
5. 记录失败时各节点的最后状态与日志；
6. 写结论：卡住时系统在尝试什么？哪一步最先失败？

**通过判据**：架构图完整，且能用行为树解释一次真实的失败过程。

## 5. 自动检查

```bash
python3 -c "seq=lambda x:'SUCCESS' if all(v=='SUCCESS' for v in x) else 'FAILURE'; fall=lambda x:'SUCCESS' if any(v=='SUCCESS' for v in x) else 'FAILURE'; assert seq(['SUCCESS','FAILURE'])=='FAILURE' and fall(['FAILURE','SUCCESS'])=='SUCCESS'; print('NAV2_BT_OK')"
```

预期输出 `NAV2_BT_OK`。

## 6. 常见故障

| 症状 | 可能原因 | 排查 |
|---|---|---|
| 规划成功但不动 | 控制器未激活/速度被平滑掉 | 查生命周期与速度话题 |
| 原地打转 | 局部代价地图把前方判为障碍 | 看局部代价地图与传感器 |
| 规划绕远路 | 全局代价地图膨胀过大 | 调膨胀半径/障碍层 |
| 导航中途停住 | 行为树进入恢复且全部失败 | 看 bt_navigator 日志 |
| TF 报错找不到 map | 定位节点未启动/未发布 | 查 TF 树与定位状态 |
| 换了目标点行为异常 | 坐标系用错（map vs odom） | 统一目标与规划坐标系 |
| 节点起来又挂 | 参数不合法，configure 失败 | 先看启动日志 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s7
- 来源：`06_软件部署与运维`、`02_架构与协议`、`C_现场踩坑`
- 产出物：Nav2 架构图 + 失败链路分析

## 9. 下一节

S7-04 · 代价地图：路径规划的「地形」是怎么算出来的。
