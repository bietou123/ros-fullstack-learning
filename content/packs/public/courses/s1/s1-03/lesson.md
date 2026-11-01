# S1-03 · 编写第一个节点（rospy）

> 验证状态：⚠ 本机未安装 ROS，本课代码与命令**未在本机执行**。请在 Noetic 环境实测后记录输出。

## 1. 现场类比

最小的远控链路只需要两件事：**有人一直发**（发布者），**有人一直收**（订阅者）。写节点就是写这两个角色，再决定它们之间传什么格式。

大多数「节点写了但不工作」，不是算法错，而是：没 `init_node`、`Rate` 用错、发布在 `while` 外面。

## 2. 核心概念

### 2.1 发布者骨架

```python
#!/usr/bin/env python3
import rospy
from std_msgs.msg import String

def main():
    rospy.init_node("rl_pub")                       # 必须有，且只能一次
    pub = rospy.Publisher("/rl_chat", String, queue_size=10)
    rate = rospy.Rate(5)                            # 5 Hz
    while not rospy.is_shutdown():
        pub.publish("hello %.2f" % rospy.get_time())
        rate.sleep()

if __name__ == "__main__":
    main()
```

### 2.2 订阅者骨架

```python
#!/usr/bin/env python3
import rospy
from std_msgs.msg import String

def cb(msg):
    rospy.loginfo("recv: %s", msg.data)

def main():
    rospy.init_node("rl_sub")
    rospy.Subscriber("/rl_chat", String, cb, queue_size=10)
    rospy.spin()                                    # 阻塞，保持回调

if __name__ == "__main__":
    main()
```

### 2.3 三个必错点

| 位置 | 错误写法 | 后果 |
|---|---|---|
| `Publisher` 在循环内创建 | 每次新建连接 | 发送延迟、内存涨 |
| `rate.sleep()` 漏掉 | CPU 打满、频率失控 | 下游节点被刷爆 |
| 回调里做重活 | 回调线程阻塞 | 消息积压、超时 |

**`queue_size` 是背压阀门**：发布太快、订阅太慢时，超过队列的旧消息会被丢弃——这是设计行为，不是 bug。

### 2.4 调试顺序

```
rostopic list → rostopic info → rostopic echo → rostopic hz → rosnode info
```

从「有没有」到「谁发的」到「内容对不对」到「频率对不对」，**不要跳步**。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/noetic/setup.bash
roscore
# 终端 2
rosrun rl_demo rl_pub.py
# 终端 3
rostopic echo /rl_chat
rostopic hz /rl_chat
rosnode info /rl_pub
```

## 4. 动手实验

**目标（40 分钟）**：跑通一对发布/订阅节点。

1. 把 2.1、2.2 的代码存进 `rl_demo/scripts/`，`chmod +x`；
2. `catkin_make && source devel/setup.bash`；
3. 终端 1 `roscore`，终端 2 `rosrun rl_demo rl_pub.py`，终端 3 `rosrun rl_demo rl_sub.py`；
4. 终端 4 执行 `rostopic hz /rl_chat`，确认约 5 Hz；
5. 把发送频率改成 50 Hz 再测一次，观察延迟与 CPU 变化。

**通过判据**：`rostopic hz` 实测频率与代码设定一致（误差 <10%），并能解释为什么订阅端 `queue_size` 设 10 时高频下会丢消息。

## 5. 自动检查

镜像 `ros:noetic-ros-base`：

```bash
source /opt/ros/noetic/setup.bash && python3 -c "import rospy; print(rospy.__version__)"
source /opt/ros/noetic/setup.bash && python3 -c "from std_msgs.msg import String; print(String._type)"
```

预期分别打印 rospy 版本与 `std_msgs/String`。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `rospy.exceptions.ROSInitException` | 没 init 或 master 未启动 | 先起 `roscore`，再 `init_node` |
| 订阅收不到 | 话题名或类型不一致 | `rostopic info` 比对类型 |
| 频率远高于设定 | 循环里没 `sleep` | 用 `rospy.Rate(...).sleep()` |
| 日志看不到 | 日志级别过滤 | `rqt_console` 或 `--ros-args` 调级别 |
| 节点一启动就退出 | 主循环写在 `if` 外或异常退出 | 看终端 traceback |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s1
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS Noetic `rospy` API（Publisher / Subscriber / Rate）
- 产出物：`rl_pub.py` + `rl_sub.py` 与 `rostopic hz` 截图

## 9. 下一节

S1-04 · topic、消息与 rostopic 诊断：从「能跑」到「能查」。
