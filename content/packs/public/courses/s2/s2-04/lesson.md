# S2-04 · service 与 action

> 验证状态：✅ 2026-11-03 在 `ros:humble-ros-base` 容器内实测 `rcl_interfaces/srv/GetParameters` 接口读取、`action`/`service` 子命令帮助均通过。该镜像**不含 `example_interfaces`**；命令示例中的 AddTwoInts / Fibonacci 需额外安装 `ros-humble-example-interfaces`（apt 可用）。

## 1. 现场类比

「切到自动模式」是一个瞬间完成的动作 → service。

「从当前位置开到目标点」是一个持续几十秒、可能中途要取消、需要看进度的动作 → action。用 service 做长任务，会出现「界面卡住等结果、超时了但车还在动」的经典事故。

## 2. 核心概念

### 2.1 三层通信选择

| 需求 | 机制 | 关键特征 |
|---|---|---|
| 持续播报 | topic | 无确认、可丢帧 |
| 一问一答 | service | 同步、无进度 |
| 长任务 | action | 有进度、可取消、有最终结果 |

### 2.2 action 的五个接口

| 接口 | 方向 | 内容 |
|---|---|---|
| goal | 客户端 → 服务端 | 目标参数 |
| result | 服务端 → 客户端 | 最终结果 |
| feedback | 服务端 → 客户端 | 周期进度 |
| status | 服务端 → 全部 | 当前状态 |
| cancel | 客户端 → 服务端 | 取消请求 |

**action 底层就是两个 service + 两个 topic**，不是新传输机制。

### 2.3 代码骨架（rclpy action server）

（示例依赖 `example_interfaces`，镜像内需先 `apt-get install -y ros-humble-example-interfaces`。）

```python
from rclpy.action import ActionServer
from example_interfaces.action import Fibonacci

class FibAction(ActionServer):
    def __init__(self, node):
        super().__init__(node, Fibonacci, "fibonacci")

    async def execute_callback(self, goal_handle):
        seq = [0, 1]
        for i in range(1, goal_handle.request.order):
            seq.append(seq[-1] + seq[-2])
            goal_handle.publish_feedback(Fibonacci.Feedback(sequence=seq))
        goal_handle.succeed()
        return Fibonacci.Result(sequence=seq)
```

要点：**feedback 里必须能反映真实进度**，否则界面上的进度条就是装饰。

### 2.4 超时与取消的设计

- 客户端设 `goal_timeout`，超时后发送 cancel，**不要只等**；
- 服务端在 `cancel_callback` 里必须真正停下动作，而不是把状态改成 canceled 就完事；
- 取消后要有明确反馈（动作真的停止了）。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

ros2 service list -t
ros2 action list -t
ros2 interface show rcl_interfaces/srv/GetParameters

# 以下两条需要额外安装：apt-get install -y ros-humble-example-interfaces
ros2 interface show example_interfaces/srv/AddTwoInts
ros2 interface show example_interfaces/action/Fibonacci

ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts "{a: 1, b: 2}"
ros2 action send_goal /fibonacci example_interfaces/action/Fibonacci "{order: 5}" --feedback
```

## 4. 动手实验

**目标（40 分钟）**：写一个可取消、有反馈的 action server。

1. 用 `example_interfaces` 的 Fibonacci 写一个 action server（见 2.3）；
2. 用 `ros2 action send_goal ... --feedback` 发目标，观察反馈；
3. 开第二个终端，在任务执行中发 `ros2 action cancel`，记录服务端日志；
4. 故意让 `execute_callback` 不响应取消，观察取消请求的实际效果；
5. 把「取消后动作是否真的停」写成结论。

**通过判据**：能说清 `succeed()`、`abort()`、`canceled()` 三种终止状态的区别。

## 5. 自动检查

镜像 `ros:humble-ros-base`：

```bash
source /opt/ros/humble/setup.bash && ros2 interface show rcl_interfaces/srv/GetParameters > /tmp/i.txt && grep -q ParameterValue /tmp/i.txt
source /opt/ros/humble/setup.bash && ros2 action --help 2>/dev/null | grep -q goal
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `action client` 一直等结果 | 服务端没起/命名空间不同 | `ros2 action list -t` 确认 |
| 取消无效 | `cancel_callback` 里没真正停 | 取消要落实到控制层 |
| feedback 不动 | 只发一次或频率过低 | 按周期发布真实进度 |
| 目标长时间无响应 | server 回调阻塞 | 回调里不做重活 |
| 服务端多次执行同一 goal | 客户端重发 | 用 goal id 去重 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s2
- 来源：`E_ROS与Linux命令手册`、`C_现场踩坑`
- 外部参考：ROS 2 Humble Actions 文档
- 产出物：可取消的 action server + 取消效果记录

## 9. 下一节

S2-05 · lifecycle 与 composition：让节点「可控地上线」。
