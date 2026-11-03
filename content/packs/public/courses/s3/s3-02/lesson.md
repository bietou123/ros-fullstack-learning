# S3-02 · xacro 参数化

> 验证状态：✅ 2026-11-03 在本地构建的 `ros:humble-xacro` 镜像（`ros:humble-ros-base` + `ros-humble-xacro`）内实测 xacro 展开与 `check_urdf` 均通过。`ros:humble-ros-base` 本身不含 xacro，需使用该扩展镜像（构建方式见 README）。

## 1. 现场类比

同一套远控系统要装到不同吨位的车上：动臂长度、铰点位置、限位全都不同。复制一份 URDF 改数值 → 三台车三个文件，改一处要同步三处，必错。

xacro 让你写**一份模型 + 一组参数**。参数来自机型配置，模型文件本身不动。

## 2. 核心概念

### 2.1 四个基本语法

```xml
<?xml version="1.0"?>
<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="rl_demo">
  <xacro:property name="arm_len" value="2.0"/>
  <xacro:property name="arm_radius" value="0.1"/>

  <xacro:macro name="cyl_link" params="name length radius">
    <link name="${name}">
      <visual>
        <geometry><cylinder length="${length}" radius="${radius}"/></geometry>
        <origin xyz="${length/2} 0 0" rpy="0 1.5708 0"/>
      </visual>
    </link>
  </xacro:macro>

  <xacro:cyl_link name="arm_link" length="${arm_len}" radius="${arm_radius}"/>
</robot>
```

| 语法 | 用途 |
|---|---|
| `<xacro:property>` | 定义变量 |
| `${...}` | 表达式取值，可做四则运算 |
| `<xacro:macro>` | 复用一段结构 |
| `<xacro:include>` | 拆分文件 |

### 2.2 从参数到模型的三条路径

```
机型参数 (yaml/命令行) → xacro 变量 → URDF → robot_state_publisher
```

命令行覆盖：`xacro model.xacro arm_len:=2.5 > /tmp/model.urdf`。

### 2.3 什么时候该参数化

- 多机型共用同一结构 → 必须；
- 只有单台、结构不变 → 不要过度抽象，URDF 直接写更清楚；
- **参数化的是尺寸与限位，不是拓扑**：拓扑变了（如四连杆改直推）应拆成不同模型。

### 2.4 校验

```bash
xacro model.xacro > /tmp/model.urdf
check_urdf /tmp/model.urdf
```

**先展开再校验**，报错行号才是 URDF 的行号，而不是 xacro 的。

## 3. 可复制命令 / 代码

```bash
source /opt/ros/humble/setup.bash

xacro --help | head -n 5
xacro /path/to/model.xacro arm_len:=2.5 > /tmp/model.urdf
check_urdf /tmp/model.urdf
```

## 4. 动手实验

**目标（35 分钟）**：把 S3-01 的两连杆模型改成参数化。

1. 把长度、半径、限位抽成 `xacro:property`；
2. 用 macro 生成两个连杆，参数分别是动臂与斗杆；
3. 默认值 `arm_len=2.0`，命令行覆盖成 `2.5`，对比生成的两个 URDF；
4. `diff` 两个文件，确认只有数值变化；
5. 故意传一个非法值（如负长度），观察 xacro/check_urdf 是否报错。

**通过判据**：能用一条命令生成两个不同尺寸的模型，且 `diff` 结果可解释。

## 5. 自动检查

镜像 `ros:humble-xacro`（基于 `ros:humble-ros-base` + `ros-humble-xacro`；`ros-base` 本身不含 xacro）。构建：

```bash
docker build -t ros:humble-xacro scripts/experiment-images/ros-humble-xacro
```

```bash
source /opt/ros/humble/setup.bash && command -v xacro
source /opt/ros/humble/setup.bash && xacro --help 2>&1 | head -n 2
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `xacro: command not found` | 没 source | source ROS 环境 |
| `${...}` 原样输出 | 命名空间没声明 | 根节点加 `xmlns:xacro` |
| 展开后检查失败 | 参数类型不对（字符串当数字） | 检查表达式 |
| 参数覆盖不生效 | 变量名拼写/作用域 | `xacro --inorder model.xacro` 排查 |
| 模型尺寸翻倍 | 长度与半长混淆 | 明确「长度」定义 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s3
- 来源：`E_ROS与Linux命令手册`
- 外部参考：ROS 2 xacro 文档
- 产出物：参数化模型 + 两个尺寸的生成对比

## 9. 下一节

S3-03 · TF2 广播器与监听器：让模型跟着真实关节动起来。
