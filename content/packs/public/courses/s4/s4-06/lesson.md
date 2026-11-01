# S4-06 · 100Hz 控制环与实时性

> 验证状态：✅ 抖动测量脚本可本地运行（纯 Python，无需 ROS）；PREEMPT_RT / CPU 隔离等系统配置**未在本机实测**。

## 1. 现场类比

「100Hz 控制」不是「平均每秒算 100 次」，而是**每一拍都必须在 10ms 内完成，并且不能偶尔迟到 30ms**。

一次 30ms 的迟到，在 1.2 m/s 的油缸上就是 36mm 的位移误差。现场表现是「动作一顿一顿」或「低速抖动」——很多人先怀疑机械，其实是控制循环被系统调度打断了。

## 2. 核心概念

### 2.1 三个指标

| 指标 | 含义 | 目标 |
|---|---|---|
| 周期 | 相邻两拍的平均间隔 | 10ms |
| 抖动 jitter | 实际间隔相对 10ms 的偏差 | 越小越好 |
| 最坏延迟 | 单次最大迟到 | 必须可接受、有上限 |

**平均值好看没有意义，要看 P99 和最坏值。**

### 2.2 常见的「不实时」来源

| 来源 | 现象 | 对策 |
|---|---|---|
| Python GC | 偶发长停顿 | 避免循环内分配对象 |
| 内存分配/页错误 | 尖峰 | 预分配、`mlockall` |
| 普通内核调度 | 被其它进程抢占 | PREEMPT_RT + 实时优先级 |
| CPU 频率调节 | 抖动变大 | `performance` governor |
| 日志/printf | 阻塞 | 循环内不打日志 |
| 网络/串口阻塞读 | 周期被拉长 | 非阻塞 + 独立线程 |

### 2.3 先测量，再优化

```python
import time

period = 0.01
t = time.perf_counter()
stamps = []
for _ in range(6000):          # 60 秒
    t += period
    while time.perf_counter() < t:
        pass                    # 忙等，避免 sleep 精度问题
    stamps.append(time.perf_counter())

d = [b - a for a, b in zip(stamps, stamps[1:])]
d.sort()
def pct(p): return d[min(len(d) - 1, int(len(d) * p))]
print(f"mean={sum(d)/len(d)*1000:.3f}ms p99={pct(0.99)*1000:.3f}ms max={d[-1]*1000:.3f}ms")
```

在普通桌面系统上，`max` 经常是 `mean` 的几倍——这就是调度抖动的证据。

### 2.4 实时化的四个动作

```
1. 内核：PREEMPT_RT（或至少 low-latency）
2. 优先级：控制线程 SCHED_FIFO，高于普通线程
3. 内存：mlockall 锁定，避免换页
4. 隔离：控制线程绑核，关掉同核上的杂活
```

**顺序不能反**：先测出抖动，再逐项加配置，每加一项复测一次。

### 2.5 与总线周期的关系

控制周期 10ms，但 CAN 帧可能是 20ms 一帧：

- 控制节点必须「保持上次值 + 超时保护」（回看 S0-07）；
- 不要为了对齐总线，把控制周期拉长到 20ms——控制环变慢会直接牺牲稳定性。

## 3. 可复制命令 / 代码

```bash
# 系统实时性配置检查
uname -a | grep -i -E 'preempt|rt'
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
chrt -p $$                       # 当前进程调度策略

# 实时性基准测试（需安装 rt-tests）
cyclictest -t1 -p 80 -i 1000 -n -l 10000
```

## 4. 动手实验

**目标（40 分钟）**：测出你机器的控制环抖动。

1. 运行 2.3 的脚本 60 秒，记录 mean / p99 / max；
2. 把「忙等」改成 `time.sleep(period)`，再测一次并对比；
3. 在循环里加 `print`，观察抖动变化；
4. 在另一个终端跑满 CPU（如 `yes > /dev/null`）再测；
5. 如果有条件，用 `chrt` 提高优先级后再测。

**通过判据**：四个场景的 p99/max 数据齐全，能指出影响最大的一项。

## 5. 自动检查

```bash
python3 -c "import time; d=[]; t=time.perf_counter()
for _ in range(1000):
    t+=0.001
    while time.perf_counter()<t: pass
    d.append(time.perf_counter())
g=[b-a for a,b in zip(d,d[1:])]; g.sort()
print('p99_ms=%.3f' % (g[int(len(g)*0.99)]*1000))"
```

预期：输出一个 `p99_ms` 数值（不同机器不同），能稳定输出即说明测量链路可用。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 平均 10ms 但车抖 | max 抖动大 | 看 P99/最坏值 |
| 偶发 50ms 停顿 | GC / 页错误 | 预分配、mlockall |
| 加日志后变差 | I/O 阻塞 | 循环内不打日志 |
| 提高优先级后更糟 | 饿死其它必要线程 | 合理分配优先级 |
| 仿真实时但实车不实时 | 环境不同 | 必须在目标机上测 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s4
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 外部参考：PREEMPT_RT、ciA 301 实时性附录
- 产出物：四场景抖动测量记录

## 9. 下一节

S4-07 · 时间同步与驱动封装：让所有数据的时间戳可信。
