# S8-02 · systemd 服务化与开机自启

> 验证状态：✅ 本机 WSL 内 systemd 正在运行，`systemctl is-system-running`、`list-units` 与 `systemd-analyze verify` 已实测；⚠ 创建并启用真实业务服务需要 sudo，**本机未做**。

## 1. 现场类比

设备断电重启，操作手等了十分钟，屏幕还是黑的——因为服务是手工在终端里起的，重启就没了。

**“能跑”和“能自己起来”是两件事。** systemd 负责后者：开机拉起、崩溃重启、日志统一、状态可查。

## 2. 核心概念

### 2.1 一个 unit 的三段

```ini
[Unit]
Description=RL control bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/rl/bin/bridge --config /etc/rl/bridge.yaml
WorkingDirectory=/opt/rl
Restart=on-failure
RestartSec=3
User=rl

[Install]
WantedBy=multi-user.target
```

| 段 | 写什么 |
|---|---|
| `[Unit]` | 描述、启动顺序、依赖 |
| `[Service]` | 怎么起、怎么重启、以谁运行 |
| `[Install]` | `enable` 时装到哪个 target |

### 2.2 常用控制命令

| 命令 | 作用 |
|---|---|
| `systemctl daemon-reload` | 改 unit 后重新加载 |
| `systemctl enable --now xxx` | 开机自启 + 立即启动 |
| `systemctl status xxx` | 运行状态与最近日志 |
| `systemctl restart xxx` | 重启 |
| `journalctl -u xxx -f` | 跟踪日志 |
| `systemd-analyze verify xxx.service` | 静态检查 unit |

**只 `enable` 不 `start`，本次不会运行；只 `start` 不 `enable`，重启后就没了。**

### 2.3 重启策略

| 值 | 行为 |
|---|---|
| `no` | 不重启 |
| `on-failure` | 非零退出/被信号杀死时重启；正常退出不重启 |
| `always` | 总是重启 |
| `unless-stopped` | 除非手动 stop，否则总是重启 |

配合 `RestartSec` 避免「崩溃—重启」死循环打满 CPU。频繁重启本身就是故障信号，要能被日志看出来。

### 2.4 启动顺序与就绪

- `After=` 只保证顺序，不保证对方「可用」；
- 网络服务用 `network-online.target` + `Wants=`；
- 业务依赖其他服务时，应用层仍要重试，不能假设对方已就绪。

### 2.5 安全与权限

- 用专用用户 `User=rl`，不用 root；
- 只给必要权限，配置文件只读；
- 环境变量用 `EnvironmentFile=`，文件权限 600；
- **unit 文件里不写明文密码。**

## 3. 可复制命令 / 代码

```bash
# 本机 systemd 状态
systemctl is-system-running

# 查看正在运行的服务
systemctl list-units --type=service --state=running --no-pager | head

# 静态检查一个 unit（临时生成，不安装）
printf '[Unit]\nDescription=rl test\n[Service]\nExecStart=/bin/true\n[Install]\nWantedBy=multi-user.target\n' > /tmp/rl-test.service; systemd-analyze verify /tmp/rl-test.service; echo EXIT=$?
```

预期：`running`；列出若干 running 服务；`EXIT=0`（unit 语法合法）。

## 4. 动手实验

**目标（35 分钟）**：把一个服务做成 systemd unit，并通过「重启仍自动运行」验收。

1. 确定可执行文件路径、配置路径、运行用户；
2. 写 unit（三段齐全），先 `systemd-analyze verify`；
3. 安装到 `/etc/systemd/system/`，`daemon-reload`；
4. `enable --now`，检查 `status` 与日志；
5. 手动 `kill` 进程，确认能按策略重启；
6. 重启系统，确认自动拉起并进入可用状态；
7. 写结论：重启耗时多少？失败时日志能在哪里看到？

**通过判据**：断电/重启后服务自动运行；人为杀死进程能恢复；日志能定位失败原因。

## 5. 自动检查

```bash
printf '[Unit]\nDescription=rl test\n[Service]\nExecStart=/bin/true\n[Install]\nWantedBy=multi-user.target\n' > /tmp/rl-test.service; systemd-analyze verify /tmp/rl-test.service; echo UNIT_OK
```

预期输出 `UNIT_OK` 且无错误信息。

## 6. 常见故障

| 症状 | 可能原因 | 排查 |
|---|---|---|
| 开机没起来 | 只 start 没 enable | `systemctl is-enabled` |
| 启动即失败 | 路径写错、权限不足、环境变量缺失 | `status` + `journalctl -u` |
| 改了 unit 不生效 | 没 daemon-reload | 重新加载后再 restart |
| 网络未就绪就启动 | 没依赖 network-online | 加 After/Wants，应用层重试 |
| 反复重启刷屏 | 崩溃循环、RestartSec 太小 | 看日志根因，加大间隔 |
| 用 root 运行 | 图省事 | 建专用用户，收权限 |
| 日志找不到 | 输出到 stdout 但没进 journal | 确认 Type 与日志配置 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s8
- 来源：`06_软件部署与运维`、`E_ROS与Linux命令手册`
- 产出物：unit 文件 + 自启验收记录

## 9. 下一节

S8-03 · 网络、VPN 与远程接入：现场连不上，后面全是空谈。
