# S10-03 · 座舱指令与安全状态机

> 验证状态：✅ 本机 Linux 实测了状态转换、非法转换拒绝与超时进入故障态；⚠ 本课状态机为软件层示例，**不能替代急停硬线回路**，真实安全功能须按相关标准由专业人员设计验证。

## 1. 现场类比

操作员松开手柄，设备还在动；故障报警后按了一下启动键，设备又跑起来了。事后查代码：状态机根本没拦住。

**指令不是「谁发都执行」，要先过优先级，再过状态门控。**

## 2. 核心概念

### 2.1 指令来源与优先级

| 优先级 | 来源 | 说明 |
|---:|---|---|
| 1 | 急停 / 安全回路 | 硬件回路，独立于软件（S6-04） |
| 2 | 安全停机 | 超时、越界、看门狗 |
| 3 | 座舱操作 | 现场操作员 |
| 4 | 远程操作 | 远控端 |
| 5 | 自动任务 | 脚本 / 上层调度 |

**低优先级永远不能覆盖高优先级。** 软件状态机只负责 2–5 层的门控。

### 2.2 状态定义

| 状态 | 含义 | 允许的动作 |
|---|---|---|
| idle | 未使能 | 仅允许 arm |
| ready | 已使能、未动作 | start / disarm |
| running | 执行中 | stop / 超时 |
| fault | 故障锁存 | 仅允许 reset |
| estop | 急停（软件镜像） | 物理复位后重新初始化 |

### 2.3 非法转换必须拒绝

状态机对每个事件只有两种结果：

1. 有定义 → 转换；
2. 无定义 → **保持原状态并记录拒绝原因**。

「忽略掉继续跑」是最危险的处理方式。

### 2.4 故障要锁存

- 进入 `fault` 后**不自动恢复**；
- `reset` 前必须确认故障原因已消除；
- 原因未消除就 reset，应再次进入 `fault`。

### 2.5 看门狗 / 死手信号

操作端持续发送心跳或使能信号。超时未收到：

```
running → fault（输出立即归零）
```

这就是 S6-05 的看门狗在指令链路上的落地。**没有死手信号的远控，不叫远控。**

### 2.6 指令链路的数据流

```
输入 → 死区/归一化（S6-01）→ 限幅/限速（S6-02）
     → 状态机门控 → 执行器模型（S10-02）
```

门控不通过时，输出必须是**明确的 0 或安全值**，不能保留上一条指令。

### 2.7 必须记录的状态日志

每次转换记录：时间、原状态、事件、新状态、来源、拒绝原因。

**没有日志的状态机，出事后无法复盘。**

## 3. 可复制命令 / 代码

```bash
# 状态机：正常流转 + 非法转换拒绝 + 超时故障
python3 -c "from itertools import accumulate; trans={'idle':{'arm':'ready'},'ready':{'start':'running','disarm':'idle'},'running':{'stop':'ready','timeout':'fault'},'fault':{'reset':'idle'}}; ev=['arm','start','timeout','start','reset','arm']; states=list(accumulate(ev, lambda s,e: trans.get(s,{}).get(e,s), initial='idle'))[1:]; rej=sum(1 for a,b in zip(['idle']+states[:-1],states) if a==b); print('states=%s rejected=%d'%(states,rej))"
```

预期：

```
states=['ready', 'running', 'fault', 'fault', 'idle', 'ready'] rejected=1
```

含义：进入 `fault` 后，`start` 被拒绝（状态保持 `fault`）；只有 `reset` 才能回到 `idle`。

## 4. 动手实验

**目标（45 分钟）**：实现并测试一个带门控的安全状态机。

1. 定义 4–5 个状态与允许的事件表；
2. 实现转换函数：合法则转换，非法则保持并计数；
3. 加入超时事件，验证 `running → fault`；
4. 验证故障锁存：`fault` 下只有 `reset` 可用；
5. 验证 reset 前原因未消除时再次进入 `fault`；
6. 为每次转换写日志字段；
7. 写结论：哪些事件必须被拒绝？日志能否还原一次故障？

**通过判据**：非法转换被拒绝且可计数；超时进入故障；故障必须显式复位。

## 5. 自动检查

```bash
python3 -c "from itertools import accumulate; trans={'idle':{'arm':'ready'},'ready':{'start':'running','disarm':'idle'},'running':{'stop':'ready','timeout':'fault'},'fault':{'reset':'idle'}}; ev=['arm','start','timeout','start','reset','arm']; states=list(accumulate(ev, lambda s,e: trans.get(s,{}).get(e,s), initial='idle'))[1:]; rej=sum(1 for a,b in zip(['idle']+states[:-1],states) if a==b); assert states[2]=='fault' and states[3]=='fault' and rej==1; print('FSM_OK')"
```

预期输出 `FSM_OK`。

## 6. 常见故障

| 症状 | 可能原因 | 排查 |
|---|---|---|
| 松手后设备继续动 | 无死手/看门狗 | 加超时，输出归零 |
| 故障后按启动又能跑 | 故障未锁存 | 加 fault 锁存与 reset |
| 远程指令覆盖现场操作 | 优先级未定义 | 写死优先级并做互斥 |
| 状态跳变无法复现 | 无转换日志 | 记录事件、来源、原因 |
| reset 后立即再故障 | 原因未消除 | reset 前检查前置条件 |
| 急停后软件状态不一致 | 软件未同步硬线状态 | 读取硬线状态并镜像 |
| 多人同时操作互相打架 | 无操作权仲裁 | 单会话 + 明确接管流程 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s10
- 来源：`03-安全设计与状态机.md`、`02_架构与协议`、`C_现场踩坑`
- 产出物：指令链路 + 状态机（含转换表与测试用例）

## 9. 下一节

S10-04 · 标定与 TF 集成：让每个坐标都有出处。
