# S0-03 · 文件系统、权限、进程与 systemd 直觉

> 验证状态：✅ 权限命令与 `systemd-run --user` 已在 Ubuntu 24.04（WSL2，systemd 为 PID 1）实测。不同发行版的 unit 目录路径略有差异，已在文中标注。

## 1. 现场类比

场景一：现场把程序拷到车上，用 `./start.sh` 能跑，重启车就没了。
场景二：日志提示 `status=203/EXEC`，你改了半天代码，其实是脚本没有执行权限。

**这两个问题都属于「进程生命周期」**：谁启动它、以什么身份、挂了谁拉起来、日志去哪看。Linux 的答案是权限 + systemd。掌握这一课，你在现场就不会再靠「重启试试」。

## 2. 核心概念

### 2.1 权限三个数字

`ls -l` 第一列如 `-rwxr-x---`：

```
-  rwx  r-x  ---
|   |    |    |
类型 属主 属组 其他人
```

三位一组，`r=4 w=2 x=1`，所以 `750` = 属主 rwx、属组 r-x、其他人无权限。

- 脚本要执行：至少属主 `x`；
- 敏感配置（密钥、证书）：`600`，只有属主可读写；
- 共享只读数据：`644`。

> 经验法则：**能 600 就不要 644，能 750 就不要 777**。`777` 在现场是排障负债，不是省事。

### 2.2 进程状态速查

`ps -ef` 的 STAT 列常见值：

| 状态 | 含义 | 现场意义 |
|---|---|---|
| `R` | 运行/可运行 | 正常 |
| `S` | 可中断睡眠 | 等待事件，正常 |
| `D` | 不可中断睡眠 | 多在等磁盘/驱动，`kill -9` 也杀不掉 |
| `Z` | 僵尸 | 父进程没收尸，查父进程 |
| `T` | 停止 | 被 `SIGSTOP` 或调试器暂停 |

### 2.3 systemd 三件套

一个服务就是一份 unit 文件，核心三段：

```ini
[Unit]
Description=Robot bridge service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=robot
WorkingDirectory=/opt/robot
ExecStart=/opt/robot/bin/bridge --config /etc/robot/bridge.yaml
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- 系统级 unit：`/etc/systemd/system/xxx.service`（需要 root 安装）；
- 用户级 unit：`~/.config/systemd/user/xxx.service`（登录用户即可，适合实验）；
- 改了 unit 必须 `systemctl daemon-reload`，否则跑的还是旧配置。

### 2.4 日志去哪了

- `systemctl status xxx` 看最近几行；
- `journalctl -u xxx -n 100 --no-pager` 看最近 100 行；
- `journalctl -u xxx -f` 实时跟踪；
- 用户级服务加 `--user`：`journalctl --user -u xxx`。

## 3. 可复制命令 / 代码

```bash
# 1) 权限实验
rm -rf /tmp/rl-s03 && mkdir -p /tmp/rl-s03
printf '#!/bin/sh\necho ok\n' > /tmp/rl-s03/run.sh
chmod 700 /tmp/rl-s03/run.sh
stat -c '%a %n' /tmp/rl-s03/run.sh     # 输出: 700 /tmp/rl-s03/run.sh
/tmp/rl-s03/run.sh                      # 输出: ok

# 2) 用 systemd 临时拉起一个服务（用户级）
systemd-run --user --unit rl-s03-demo --collect /bin/sh -c 'sleep 45'
systemctl --user is-active rl-s03-demo  # 输出: active
systemctl --user status rl-s03-demo --no-pager | head -6

# 3) 看日志
journalctl --user -u rl-s03-demo -n 20 --no-pager
```

## 4. 动手实验

**目标（25 分钟）**：把一个脚本变成「可查询状态、可看日志」的服务。

1. 跑通上一节三段命令；
2. 把 `sleep 45` 改成你自己的任意脚本（例如每 2 秒打印一行时间）；
3. 用 `systemctl --user status` 找到 Main PID，再用 `ps -p <PID> -o pid,stat,cmd` 观察状态；
4. 用 `systemctl --user stop` 停掉，再用 `is-active` 确认变为 `inactive`。

**通过判据**：能解释「`systemd-run --collect` 和写 unit 文件再 `enable` 有什么区别」。

## 5. 自动检查

「实验」页签会执行：

```bash
test "$(stat -c '%a' /tmp/rl-s03/run.sh)" = "700"
systemctl --user is-active --quiet rl-s03-demo
```

第二条依赖用户级 systemd（WSL 需开启 systemd；纯容器环境没有，会显示失败——这是环境限制，不是课程内容错误）。

## 6. 常见故障

| 报错 | 含义 | 处理 |
|---|---|---|
| `status=203/EXEC` | 找不到或没有执行权限 | `ls -l` 看 x 位；检查 shebang |
| `status=217/USER` | unit 里的 User 不存在 | `id 用户名`，改 unit |
| `status=200/CHDIR` | WorkingDirectory 不存在 | 先建目录或改路径 |
| `status=1/FAILURE` | 程序自己退出 1 | `journalctl -u xxx -n 100` 看程序日志 |
| 改了配置不生效 | 没 daemon-reload | `systemctl daemon-reload` 后 restart |
| 用户服务重启后消失 | 没 `loginctl enable-linger` | 需要常驻再开启 linger |

> ⚠ 冲突提示：`systemd-run` 生成的 transient unit 在 `/run/user/<uid>/systemd/transient/`，而写文件的 unit 在 `~/.config/systemd/user/`。两者都能用，但排障路径不同，别混。

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s0
- 来源：`E_ROS与Linux命令手册`
- 产出物：服务化小实验记录

## 9. 下一节

S0-04 · 网络：IP / 路由 / 端口 / SSH / 防火墙。
