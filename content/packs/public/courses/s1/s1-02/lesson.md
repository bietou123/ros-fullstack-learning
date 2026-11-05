# S1-02 · 工作空间与 catkin 包

> 验证状态：✅ 2026-11-04 在 `ros:noetic-ros-base` 容器内实测：`catkin_make` 建工作空间、`catkin_create_pkg` 生成 `package.xml` / `CMakeLists.txt`、`rospack find` 定位新包均通过。

## 1. 现场类比

车端程序不是「一个 hello.py」，而是十几个包互相依赖。包放错地方、`devel/setup.bash` 没 source，就会出现「明明编译成功，`rosrun` 却找不到包」。

工作空间的本质是**一套隔离的环境变量**：`source devel/setup.bash` 之后，终端才知道去哪儿找你的包。

## 2. 核心概念

### 2.1 目录结构

```
catkin_ws/
├── src/                  ← 你自己写的东西只放这里
│   └── rl_demo/
│       ├── package.xml   ← 包的身份与依赖
│       ├── CMakeLists.txt
│       ├── src/
│       ├── launch/
│       └── scripts/
├── build/                ← 编译中间产物（别提交 Git）
├── devel/                ← 生成的环境脚本与产物（别提交 Git）
└── install/
```

### 2.2 一次编译到底改了什么

| 步骤 | 命令 | 作用 |
|---|---|---|
| 建包 | `catkin_create_pkg rl_demo rospy std_msgs` | 生成 `package.xml` + `CMakeLists.txt` |
| 编译 | `catkin_make` | 读依赖、生成 devel 空间 |
| 激活 | `source devel/setup.bash` | 把当前工作空间加进 `ROS_PACKAGE_PATH` |
| 验证 | `rospack find rl_demo` | 能打印路径即成功 |

**新开一个终端必须重新 source**——这是新手最常见的「昨天还好好的」问题。

### 2.3 依赖写在哪

`package.xml` 决定「运行时需要什么」，`CMakeLists.txt` 决定「编译时链接什么」。Python 包通常只需 `package.xml` 里的 `<depend>` 与 `<exec_depend>`，C++ 还要在 `CMakeLists.txt` 里 `find_package` + `catkin_package`。

`⚠ 冲突`：不少网上教程让你直接手动写 `package.xml`，跳过 `catkin_create_pkg`。能跑，但依赖声明容易漏，换机器就崩——课程要求用生成器起步。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/noetic/setup.bash
mkdir -p ~/catkin_ws/src && cd ~/catkin_ws
catkin_make                      # 第一次先编译空空间
cd src
catkin_create_pkg rl_demo rospy std_msgs
cd ..
catkin_make
source devel/setup.bash
rospack find rl_demo
```

## 4. 动手实验

**目标（30 分钟）**：建包、改依赖、编译、验证。

1. 按上面命令建 `rl_demo`；
2. 打开 `package.xml`，把 `<description>` 改成你自己的说明，给 `<maintainer>` 填邮箱；
3. 加依赖 `std_srvs`：`catkin_create_pkg` 已生成的包里手工在 `package.xml` 加 `<depend>std_srvs</depend>`；
4. 重新 `catkin_make`，确认无报错；
5. 在包里建 `scripts/hello.py`（内容见下），`chmod +x`，`catkin_make` 后 `rosrun rl_demo hello.py`。

```python
#!/usr/bin/env python3
import rospy
if __name__ == "__main__":
    rospy.init_node("hello")
    rospy.loginfo("rl_demo is ready")
```

**通过判据**：`rospack find rl_demo` 有输出，`rosrun rl_demo hello.py` 能打印日志。

## 5. 自动检查

镜像 `ros:noetic-ros-base`：

```bash
source /opt/ros/noetic/setup.bash && which catkin_make
source /opt/ros/noetic/setup.bash && which catkin_create_pkg
```

`rospack find std_msgs` 也可作为补充判据。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `catkin_make: command not found` | 没 source | `source /opt/ros/noetic/setup.bash` |
| `rospack find` 找不到自己的包 | 没 source devel | `source ~/catkin_ws/devel/setup.bash` |
| 编译报缺依赖 | `package.xml` 少 `<depend>` | 补依赖后重新 `catkin_make` |
| 多工作空间互相覆盖 | 后 source 的优先 | 用 `ROS_PACKAGE_PATH` 检查顺序 |
| 改了 CMakeLists 不生效 | 增量缓存 | `rm -rf build devel` 后重编（确认无未保存产物） |
| `scripts/*.py` 无法执行 | 没有可执行位 | `chmod +x` |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s1
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS Noetic 官方文档（catkin/Tutorials）
- 产出物：`rl_demo` 包与编译记录

## 9. 下一节

S1-03 · 编写第一个节点（rospy）：让包真正开始收发。
