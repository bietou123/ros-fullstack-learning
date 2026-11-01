# S0-02 · Linux 终端最小必备

> 验证状态：✅ 本课命令已在 Ubuntu 24.04（WSL2）实测通过。发行版差异不影响这些基础命令。

## 1. 现场类比

现场只有一张控制台截图、一段日志，没人给你 IDE。**Linux 终端就是你的听诊器**：不用图形界面，靠十几条命令就能判断「进程还在不在、端口通不通、日志里第一处错误是什么」。

本节不追求命令大全，只练 12 条高频命令和 3 个组合套路。练熟之后，S4 看 CAN、S8 查部署都会快一倍。

## 2. 核心概念

### 2.1 三个永恒问题

| 问题 | 首选命令 | 判读 |
|---|---|---|
| 文件在哪、有多大？ | `ls -lh`、`du -sh`、`find` | 注意时间戳和权限 |
| 进程活没活？ | `ps -ef`、`pgrep` | 看 PID、父进程、启动参数 |
| 日志里错在哪？ | `grep -n`、`tail -f` | 先找第一条 error，不看最后一条 |

### 2.2 必会 12 条

1. `pwd` 当前目录
2. `ls -lah` 列表（含隐藏文件、人类可读大小）
3. `cd -` 回到上一个目录
4. `cp -a` 保留属性复制
5. `mv` 移动/改名
6. `rm -i` 删除前确认（**不要**对不确定的目录用 `rm -rf`）
7. `grep -rn "关键字" .` 递归搜索
8. `find . -name "*.log" -mmin -60` 找一小时内改过的日志
9. `head -n 50` / `tail -n 50` 看头尾
10. `ps -ef | grep 进程名` 查进程
11. `ss -tlnp` 查监听端口
12. `df -h` / `du -sh *` 查磁盘占用

### 2.3 三个组合套路

```bash
# 套路一：日志定位——从最后 200 行里找第一次错误
tail -n 200 app.log | grep -n -i -E "error|fail|timeout" | head

# 套路二：端口占用——谁抢了 8080
ss -tlnp | grep ':8080'

# 套路三：大文件——当前目录谁最占空间
du -h --max-depth=1 . | sort -h | tail -n 10
```

## 3. 可复制命令 / 代码

以下整段可直接粘贴（会在 `/tmp/rl-s02` 建实验目录，不影响系统）：

```bash
rm -rf /tmp/rl-s02
mkdir -p /tmp/rl-s02/logs
cd /tmp/rl-s02
printf 'boot ok\nimu timeout\ncan error\n' > logs/app.log

grep -n 'error' logs/app.log        # 输出: 3:can error
ls -la                               # logs 目录 + 当前目录项
du -sh logs                          # 目录占用
tail -n 2 logs/app.log               # 只看最后两行
```

## 4. 动手实验

**目标（20 分钟）**：在实验目录里完成一次「找错误 → 看进程 → 查端口」的完整排查。

1. 执行上一节整段命令；
2. 用 `grep -n -i timeout logs/app.log` 找到超时行，记下行号；
3. 用 `ps -ef | head` 观察 PID 1 是什么（桌面系统通常是 systemd）；
4. 用 `ss -tlnp | head` 找任意一个监听端口，写下端口号和进程名；
5. 用 `find /tmp/rl-s02 -name "*.log" -mmin -10` 确认日志是刚生成的。

**通过判据**：你能不看笔记写出「找今日修改过的日志」和「查端口占用」两条命令。

## 5. 自动检查

点击本页「实验」页签运行，等价于：

```bash
test -f /tmp/rl-s02/logs/app.log
grep -q 'can error' /tmp/rl-s02/logs/app.log
```

两条都返回 0 才算通过。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `command not found` | 命令没装或不在 PATH | `command -v 命令`；`echo $PATH` |
| `Permission denied` | 权限不足 | 看 `ls -l`；必要时 `sudo`，先想清楚再执行 |
| `No such file or directory` | 路径错/相对路径 | `pwd`、`ls` 逐级确认 |
| `grep` 中文乱码 | 终端编码或文件编码 | `file 文件名`；`locale` |
| `ss` 看不到进程名 | 非 root 看不到其他用户进程 | `sudo ss -tlnp` |

> ⚠ 冲突提示：`ss` 与旧命令 `netstat` 的输出列含义不同（`Local Address` 已含端口）。照抄旧资料容易把端口看错。

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s0
- 来源：`E_ROS与Linux命令手册`
- 产出物：30 条命令实操清单

## 9. 下一节

S0-03 · 文件系统、权限、进程与 systemd：让脚本在重启后还活着。
