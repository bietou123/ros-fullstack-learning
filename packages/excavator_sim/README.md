# excavator_sim

20 t 级履带式液压挖掘机的**运动学**演示：URDF 模型 + 脚本化的挖装循环，在 rviz2 里播放。

不含动力学、不含液压模型、不依赖 Gazebo —— 目的是在没有独立显卡、只有软件渲染的
设备上（本项目测试机：小米 Pad 6 Pro / Ubuntu arm64）也能看清楚四轴联动关系：
**回转 → 动臂 → 斗杆 → 铲斗**。

## 模型

| 关节 | 类型 | 轴 | 范围（rad） | 速度上限（rad/s） | 含义 |
| --- | --- | --- | --- | --- | --- |
| `swing_joint` | revolute | z | -3.1416 … 3.1416 | 1.2 | 回转，正 = 俯视逆时针 |
| `boom_joint` | revolute | y | -1.15 … 0.36 | 0.7 | 动臂，正 = 臂头向下 |
| `arm_joint` | revolute | y | -0.35 … 2.60 | 1.2 | 斗杆，正 = 向机器侧收 |
| `bucket_joint` | revolute | y | -1.10 … 1.20 | 1.8 | 铲斗，正 = 卸料张开 |

几何全部是 `urdf/meshes/` 下的 OBJ，由 `tools/gen_meshes.py` **程序化生成**
（俯视/侧视轮廓挤出 + 回转体，没有一处是方盒子拼的），整机约 4.3 k 顶点 / 7.6 k 三角面：

- 动臂有脚销、折点、臂头三点定出的**上下弦轮廓和弓高**，不是一根直杆；
- 配重是**俯视后缘大圆弧 + 直侧壁 + z 向近竖直 + 上下各 3 cm 小倒角**的放样体
  （尾部回转半径 2.75 m）；
- 驾驶室是封闭斜面舱：后倾前风挡、窄黑窗框、门窗分区、紧凑顶棚、黄色下裙，
  玻璃拆成六块独立窗面（`cab_glass.obj`），不跟骨架共用一个黑盒子；
- 铲斗有斗壳、D 形侧板、切削刃加强条、五枚离散斗齿。

**外形是归一化估计值，不是 OEM 实测，也不是柳工 922 的测绘复刻。** 尺寸取自公开
整机参数 + 同级参考照片（小松 PC210LC-11）上"脚销→臂头"弦的归一化量测：
履带长 4.45 m、履带板宽 0.60 m、轨距 2.20 m、驾驶室顶约 2.96 m、动臂 5.70 m、
斗杆 2.95 m、铲斗宽 1.24 m。别拿它做干涉校核。几何参数表见 `excavator_sim/design.py`。

参考照片**不在本仓库内**（无分发权，且与渲染图机型不同、带透视，做不了像素级标定）。

### 油缸

三组油缸（动臂/斗杆/铲斗）都是"**缸筒 revolute 铰在上一级 + 活塞杆 prismatic 滑出**"
的两段式，`excavator_anim` 每帧按铰点几何算出 pivot 角和伸缩量一起发布。
铰点、缸筒长、杆长、限位全部由 `excavator_sim/design.py` 的 `CYLINDERS` 导出：

```bash
python3 -m excavator_sim.cylinders      # 打印可直接抄进 URDF 的 limit
```

URDF 里那三组 `<limit>` 是密采样全关节行程后加的余量（满伸余量 ≥ 10 mm），
**别手改**：改 `design.py` 后重跑上面的命令并同步 URDF。

## 姿态

`excavator_sim/motion.py` 的 `STATIC_POSES` 是单一来源（预览、评审拼图、校验都从
这里取）：`transport` 转场抬臂、`park` 平地停放、`dig` 掘削贴地、`lift` 高举。
`park` 是剪影测量的基准姿态 —— 总长 9.79 m、最高点 3.25 m、高/长 = 0.333，
对得上 20 t 级真机转场/停放的 9.6 m × 3.0~3.2 m。

## 校验

```bash
python3 tools/validate_kinematics.py                  # 资源 / 网格 / URDF / 运动
python3 tools/validate_kinematics.py --prefix install # 改测**已安装**的 share 目录
python3 -m excavator_sim.motion 120                   # 静态姿态 + 关键帧采样复核
```

validator 查四组：`package://` 资源齐全（装出来的包少了 mesh 就是静默丢失）、
网格共享边绕序一致且无退化面、URDF 与 `design.py`/`CYLINDERS` 一致、关节限位
与齿尖不穿地。**判据不放宽**：测试失败就改模型，不改判据。

## 预览与评审拼图

```bash
python3 tools/preview_render.py       # -> build/preview/<pose>_<view>.png（4 姿态 × 3 视角）
python3 tools/review_sheet.py         # -> build/review/sheet.png（含归一化剪影与铰点）
```

`build/` 已被 `.gitignore` 排除。评审拼图的测量面板按**总长 = 1.000** 归一化，
标注为 "normalized estimates, not OEM measurements"。

## 运行

```bash
colcon build --packages-select excavator_sim
source install/setup.bash
ros2 launch excavator_sim excavator.launch.py
```

只要数据不要窗口（无显示器 / 远程验证）：

```bash
ros2 launch excavator_sim excavator.launch.py rviz:=false
ros2 topic hz /joint_states          # 30 Hz
ros2 topic echo /tf --once           # robot_state_publisher 算出来的 TF
```

调速：

```bash
ros2 launch excavator_sim excavator.launch.py speed:=0.4   # 慢动作
```

## 挖装循环

`excavator_anim` 按关键帧线性插值，一轮 12.4 s：
待命 → 伸臂下斗 → 收斗挖掘 → 提臂离地 → 带载回转 → 卸料张斗 → 收斗 → 回转归位。

关键帧在 `excavator_sim/motion.py` 的 `KEYFRAMES`，每项是 `(该段绝对时刻 s, {关节: 角度})`。
时间轴同时受速度限位约束（峰值必须低于 URDF 的 `<limit velocity>`）；上一版卸料段
1.0 s 内抖 1.95 rad 超限，解法是拉长该段，**不是放宽限位**。

## 已知限制

- 没有碰撞、没有动力学、没有履带运动，机器本体固定在地面原点。
- 没有 Gazebo 版本：平板这类设备装 Gazebo 后软件渲染基本跑不动，属于有意取舍。
- rviz 在 Wayland 会话下必须 `GDK_BACKEND=x11`，launch 文件里已固化。
- 铲斗连杆目前是简化的单铰直连；H-link + dogbone 四连杆尚未建模。

## 授权

Apache-2.0。
