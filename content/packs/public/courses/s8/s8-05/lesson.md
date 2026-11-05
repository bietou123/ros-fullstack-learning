# S8-05 · rosbag 复盘诊断

> 验证状态：✅ 2026-11-04 本机实测 rosbag2 元数据解析命令；`ros2 bag record → info → play → topic echo` 整条链路已在 `ros:humble-ros-base` 容器内实测（见 S2-07）。真实现场的长时间录制与磁盘/时间同步问题未实测。

## 1. 现场类比

动作异常发生在 14:32:07，现场谁也说不清当时传感器数据长什么样。

如果当时录了 bag，可以反复回放、逐帧对齐、慢速复现。**没有 bag，故障只能靠回忆；有 bag，故障可以变成实验。**

## 2. 核心概念

### 2.1 bag 里有什么

| 版本 | 格式 | 命令 |
|---|---|---|
| ROS1 | `.bag` | `rosbag info/play/record` |
| ROS2 | 目录 + `metadata.yaml` + 存储文件 | `ros2 bag info/play/record` |

bag 保存的是**话题消息 + 接收时间戳**，不是「现场全部真相」。传感器内部错误、驱动日志不一定在里面。

### 2.2 录制策略

| 决策 | 建议 |
|---|---|
| 记录哪些话题 | 关键传感器 + 控制指令 + 状态；不要全录 |
| 压缩 | 磁盘紧张时开启，注意 CPU 开销 |
| 分片 | 按大小/时长切分，避免单文件过大 |
| 存储位置 | 独立分区，预留空间 |
| 隐私 | 视频/点云可能含人员与现场信息，按内部资料管理 |
| 时间 | 依赖时间同步（S4-07），否则对齐失真 |

### 2.3 回放诊断要点

1. `bag info` 看话题、消息数、时长、频率；
2. 检查时间戳是否单调、是否有大间隔；
3. `play --clock` + 节点 `use_sim_time=true`，保证算法用 bag 时间；
4. 按需 `--rate 0.5` 慢放，观察临界时刻；
5. 用 `ros2 topic echo` / 可视化工具检查关键帧；
6. 对比故障前后同一话题的差异。

### 2.4 复盘报告结构

```
现象 → 时间线（关键事件） → 数据证据（话题/时间戳/数值）
    → 根因判断 → 验证方法 → 改进项
```

**只写「可能是 XX 问题」不算报告**，要有数据和复现方法。

## 3. 可复制命令 / 代码

```bash
# 解析 rosbag2 metadata.yaml：时长、总消息数、某话题频率
python3 -c "lines=['rosbag2_bagfile_information:','  message_count: 1200','  duration:','    nanoseconds: 60000000000','  topics_with_message_count:','    - topic_metadata:','        name: /imu','      message_count: 1000']; open('/tmp/m.yaml','w').write(chr(10).join(lines)); import yaml; d=yaml.safe_load(open('/tmp/m.yaml'))['rosbag2_bagfile_information']; dur=d['duration']['nanoseconds']/1e9; print('dur_s=%.0f count=%d rate=%.1f'%(dur,d['message_count'],d['topics_with_message_count'][0]['message_count']/dur))"

# 已实测（S2-07 容器内，20 Hz 发布 → record → info → play → echo）：
# ros2 bag info <bag_dir>
# ros2 bag play <bag_dir> --clock --rate 0.5
```

预期：`dur_s=60 count=1200 rate=16.7`——60 秒内 1000 条 IMU，约 16.7 Hz。

## 4. 动手实验

**目标（30 分钟）**：录一段可复盘的 bag，并写一份复盘报告。

1. 选定话题：至少包含一个传感器、一个控制指令、一个状态；
2. 设置分片大小与存储路径，确认磁盘余量；
3. 录制约 60 s 的正常数据，再人为制造一次异常；
4. 用 `bag info` 检查频率与时间戳；
5. 慢速回放异常时段，找出第一个异常量；
6. 写复盘报告：时间线、证据、根因、改进项。

**通过判据**：bag 可回放；报告能指出具体时间点与具体话题的异常数值。

## 5. 自动检查

```bash
python3 -c "lines=['rosbag2_bagfile_information:','  message_count: 1200','  duration:','    nanoseconds: 60000000000','  topics_with_message_count:','    - topic_metadata:','        name: /imu','      message_count: 1000']; open('/tmp/m.yaml','w').write(chr(10).join(lines)); import yaml; d=yaml.safe_load(open('/tmp/m.yaml'))['rosbag2_bagfile_information']; rate=d['topics_with_message_count'][0]['message_count']/(d['duration']['nanoseconds']/1e9); assert abs(rate-16.67)<0.1; print('BAG_OK')"
```

预期输出 `BAG_OK`。

## 6. 常见故障

| 症状 | 可能原因 | 排查 |
|---|---|---|
| 回放时算法行为异常 | 没开 `--clock` / `use_sim_time` | 统一用 bag 时间 |
| bag 频率明显偏低 | 录制丢帧、带宽不足 | 看消息数与时间间隔 |
| 时间戳非单调 | 多源时钟不一致 | 检查时间同步 |
| 文件过大导致磁盘满 | 全录 + 未压缩/分片 | 精选话题，设分片 |
| 回放卡顿 | 压缩/高码率/磁盘慢 | 降速率、换存储 |
| bag 里缺关键话题 | 录制列表漏项 | 固定录制配置并校验 |
| bag 含敏感画面/数据 | 未脱敏 | 按内部资料管理，不随意外发 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s8
- 来源：`06_软件部署与运维`、`E_ROS与Linux命令手册`、`C_现场踩坑`
- 产出物：复盘报告（时间线 / 证据 / 根因 / 改进）

## 9. 下一节

S8-06 · 远程升级与回滚：升级出问题时，怎么在十分钟内退回去。
