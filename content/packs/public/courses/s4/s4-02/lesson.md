# S4-02 · SocketCAN 与 vcan 实战

> 验证状态：✅ 2026-11-04 本机 Linux 实测 `socket.AF_CAN` / `CAN_RAW` 存在（SocketCAN 内核支持）；✅ 2026-11-06 在 QEMU 虚拟机（Ubuntu 24.04 云镜像，内核 `6.8.0-147-generic`，加载 `vcan` 模块）实测 vcan0 创建并 up、`cansend` 两帧均被 `candump` 捕获、Python SocketCAN 发送 1 帧并收到 2 帧（自发回环与 `cansend` 帧）；⚠ 本机 WSL2 内核未提供 `vcan` 模块（`modprobe vcan` 报 `Module vcan not found`），练习需用带 CAN 模块的常规 Linux 内核或虚拟机；真实总线时序、负载与错误帧仍需实车或硬件回环验证。

## 1. 现场类比

调试 CAN 有三条路：上实车、用 CAN 分析仪、用虚拟 CAN。

前两条成本高、风险大。**vcan 让你在笔记本上凭空造一条 CAN 总线**，收发、抓包、压测全部能在办公室完成。学 SocketCAN 的价值是：一套代码，笔记本和实车只改一个接口名。

## 2. 核心概念

### 2.1 SocketCAN 是什么

Linux 把 CAN 控制器抽象成网络接口（`can0`），用 BSD socket 收发。于是：

- 可以用 `ip` 命令配接口；
- 可以用标准 socket API 编程；
- 可以用 `candump` / `cansend` 这类通用工具。

### 2.2 vcan 的三步

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

之后 `vcan0` 就像一个普通 CAN 接口：发出去的帧，同机所有打开 `vcan0` 的进程都能收到。

> 提示：WSL2 的微软官方内核通常不带 `vcan` 模块（`modprobe vcan` 会报 `Module vcan not found`），容器内也无法绕过（共享宿主内核）。练习请用带 CAN 模块的常规 Linux 内核；没有实机时，可用 QEMU 启动 Ubuntu 云镜像（generic 内核，安装 `linux-modules-extra-$(uname -r)` 后有 `vcan` 模块），在虚拟机里完成本节实验，否则后述 `candump` / `cansend` 会直接失败，而不是伪造成功。

### 2.3 常用工具

| 工具 | 作用 | 示例 |
|---|---|---|
| `cansend` | 发一帧 | `cansend vcan0 123#DEADBEEF` |
| `candump` | 收帧 | `candump vcan0` |
| `cangen` | 造随机流量压测 | `cangen vcan0 -g 10` |
| `canbusload` | 算负载 | `canbusload vcan0@500000` |

`cansend` 的格式：`ID#数据`，数据是十六进制字节串；扩展帧写成 `12345678#...` 且加 `-x` 选项或使用更长 ID。

### 2.4 用 Python 收发（socketcan）

```python
import socket, struct

s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
s.bind(("vcan0",))

# (can_id, can_mask, len, pad, pad, pad, data[8])
frame = struct.pack("=IB3x8s", 0x123, 8, bytes([1,2,3,4,5,6,7,8]))
s.send(frame)

data, addr = s.recvfrom(16)
can_id, can_dlc = struct.unpack("=I3x", data[:8])[0], data[4]
print(hex(can_id), can_dlc, data[8:8+can_dlc].hex())
```

**注意**：`struct` 格式与字节布局必须严格对齐，错一位就收不到。

### 2.5 什么时候不能用 vcan

vcan 不做仲裁、不模拟错误帧、不模拟总线负载的真实时序。**时序相关的结论（延迟、抖动）必须在实车或硬件回环上验证。**

## 3. 可复制命令 / 代码

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
ip -details link show vcan0

# 终端 1
candump vcan0
# 终端 2
cansend vcan0 123#DEADBEEF
cansend vcan0 181#00102030405060
```

## 4. 动手实验

**目标（35 分钟）**：在 vcan 上完成一次双向收发。

1. 建 `vcan0` 并确认 `state UP`；
2. 终端 1 `candump vcan0`，终端 2 发三帧不同 ID 的报文；
3. 用 `cangen vcan0 -g 5` 造 5ms 周期流量，观察 `candump` 输出速度；
4. 用 2.4 的 Python 脚本收一帧并打印；
5. 记录 vcan 下你能观察到、但实车才有的差异（至少两条）。

**通过判据**：Python 脚本能收到 `cansend` 发出的帧，且能说出 vcan 与真实总线的两条差异。

## 5. 自动检查

本节需要 root 与内核模块，课程自动检查只在 Linux 主机上提供：

```bash
ip -details link show vcan0
candump --version
```

没有 vcan 或 can-utils 时命令失败属于预期，请按第 3 节创建。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `RTNETLINK answers: Operation not permitted` | 无权限 | `sudo` |
| `Cannot find device vcan0` | 模块未加载/未创建 | `modprobe vcan`、`ip link add` |
| 发出去收不到 | 接口未 up / 绑定错接口 | `ip link show`、`bind(("vcan0",))` |
| Python 报 `Protocol not supported` | 内核无 CAN 支持 | 换内核或用硬件适配器 |
| 容器里创建失败 | 缺 `CAP_NET_ADMIN` | 用 `--privileged` 仅限本地测试 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s4
- 来源：`E_ROS与Linux命令手册`
- 外部参考：Linux SocketCAN 文档、can-utils
- 产出物：vcan 收发脚本 + 实测记录

## 9. 下一节

S4-03 · CANopen 基础：CAN 之上的「设备语言」。
