import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const base = path.join(root, 'content/packs/public/courses')

export const stages = [
  { id: 's0', title: '地图与工具', desc: '从整机架构到 Linux / Git / Docker / 安全底线', lessons: [
    ['S0-01', '机器人全栈地图：从座舱指令到电磁阀', 30, 'teach', '手绘数据流图'],
    ['S0-02', 'Linux 终端最小必备', 45, 'teach', '30 条命令实操'],
    ['S0-03', '文件系统、权限、进程与 systemd 直觉', 40, 'teach', '服务化小实验'],
    ['S0-04', '网络：IP / 路由 / 端口 / SSH / 防火墙', 40, 'teach', '跨机连通实验'],
    ['S0-05', 'Git：分支、回滚与现场版本管理', 35, 'teach', '冲突解决演练'],
    ['S0-06', 'Docker：镜像、容器、挂载、网络', 45, 'teach', 'ROS 容器跑通'],
    ['S0-07', '机器人四层架构与数据流', 30, 'teach', '分层排障练习'],
    ['S0-08', '安全底线：急停、看门狗、权限边界', 30, 'teach', '安全检查表'],
  ]},
  { id: 's1', title: 'ROS1 核心', desc: '工作空间、节点、topic、service、launch、rosbag、TF', lessons: [
    ['S1-01', 'ROS1 世界观：master / node / topic', 30, 'teach', '节点图'],
    ['S1-02', '工作空间与 catkin 包', 35, 'teach', '自定义包'],
    ['S1-03', '编写第一个节点（rospy）', 40, 'teach', '发布者 / 订阅者'],
    ['S1-04', 'topic、消息与 rostopic 诊断', 35, 'teach', '消息抓取'],
    ['S1-05', 'service、param、launch', 40, 'teach', '参数化启动'],
    ['S1-06', 'rosbag 录制与回放', 30, 'teach', '诊断用 bag'],
    ['S1-07', 'TF 入门与 RViz', 40, 'teach', 'TF 树'],
  ]},
  { id: 's2', title: 'ROS2 核心与迁移', desc: 'rclpy、QoS、action、lifecycle、composition、DDS、bag、bridge', lessons: [
    ['S2-01', 'ROS2 架构：DDS 与节点发现', 30, 'teach', '发现机制实验'],
    ['S2-02', 'colcon 工作空间与包', 35, 'teach', 'ament_python 包'],
    ['S2-03', 'rclpy 节点与 QoS', 40, 'teach', 'QoS 对照表'],
    ['S2-04', 'service 与 action', 40, 'teach', '长任务 action'],
    ['S2-05', 'lifecycle 与 composition', 35, 'teach', '受管节点'],
    ['S2-06', 'launch.py 与参数文件', 30, 'teach', '多节点启动'],
    ['S2-07', 'ros2 bag 与诊断', 30, 'teach', '回放排障'],
    ['S2-08', 'ROS1→ROS2 迁移与 bridge', 45, 'teach', '迁移对照表'],
  ]},
  { id: 's3', title: '建模与坐标', desc: 'URDF / xacro、TF2、RViz、四连杆几何', lessons: [
    ['S3-01', 'URDF 基础：link 与 joint', 35, 'teach', '三连杆模型'],
    ['S3-02', 'xacro 参数化', 35, 'teach', '参数化模型'],
    ['S3-03', 'TF2 广播器与监听器', 35, 'teach', '坐标查询工具'],
    ['S3-04', 'RViz 与 robot_state_publisher', 30, 'teach', '可视化'],
    ['S3-05', '挖掘机四连杆几何建模', 40, 'teach', '几何草图'],
    ['S3-06', '挖机关节链 URDF 实战', 45, 'teach', '可动挖机模型'],
  ]},
  { id: 's4', title: '硬件接口', desc: 'CAN / vcan、CANopen、串口、PLC 报文、100Hz、时间同步', lessons: [
    ['S4-01', 'CAN 物理层与帧结构', 35, 'teach', '帧解析练习'],
    ['S4-02', 'SocketCAN 与 vcan 实战', 45, 'teach', '收发脚本'],
    ['S4-03', 'CANopen 基础', 30, 'teach', 'PDO / SDO 练习'],
    ['S4-04', '串口、RS485 与 Modbus RTU', 35, 'teach', '虚拟串口'],
    ['S4-05', 'PLC / VCU 报文与位域', 40, 'teach', '位域解码器'],
    ['S4-06', '100Hz 控制环与实时性', 40, 'teach', '抖动测量'],
    ['S4-07', '时间同步与驱动封装', 35, 'teach', '驱动包骨架'],
  ]},
  { id: 's5', title: '感知与标定', desc: 'IMU、LiDAR、Camera、外参、20 点触地法、符号核对', lessons: [
    ['S5-01', 'IMU 原理、噪声与安装方向', 35, 'teach', '静止噪声测试'],
    ['S5-02', 'LiDAR 驱动与点云', 35, 'teach', '点云可视化'],
    ['S5-03', 'Camera 驱动与图像管线', 30, 'teach', '图像延迟测量'],
    ['S5-04', '外参标定原理与工具', 40, 'teach', '手眼标定小实验'],
    ['S5-05', '挖掘机连杆 + IMU 外参标定', 45, 'teach', '仿真标定结果'],
    ['S5-06', '20 点触地法与误差判据', 40, 'teach', '误差分析报告'],
    ['S5-07', '坐标系、欧拉序与符号核对', 40, 'teach', '符号核对表'],
  ]},
  { id: 's6', title: '控制与安全', desc: '遥操映射、限幅、状态机、三级停机、看门狗、故障注入', lessons: [
    ['S6-01', '遥操映射：手柄 → 关节速度', 35, 'teach', '映射表'],
    ['S6-02', '限幅与斜坡', 35, 'teach', '限幅器'],
    ['S6-03', '状态机设计', 40, 'teach', '三态机'],
    ['S6-04', '三级停机与急停链路', 35, 'teach', '停机链路图'],
    ['S6-05', '看门狗与心跳', 35, 'teach', '超时保护'],
    ['S6-06', '故障注入与恢复测试', 40, 'teach', '6 类故障报告'],
    ['S6-07', '安全验收清单', 30, 'teach', '验收表'],
  ]},
  { id: 's7', title: '导航与定位', desc: 'SLAM、定位、Nav2、代价地图、调参', lessons: [
    ['S7-01', 'SLAM 概念与建图', 35, 'teach', '小场景地图'],
    ['S7-02', '定位与地图维护', 35, 'teach', '定位收敛记录'],
    ['S7-03', 'Nav2 架构', 40, 'teach', '架构图'],
    ['S7-04', '代价地图', 35, 'teach', '参数对照'],
    ['S7-05', '路径跟踪与调参', 40, 'teach', '调参表'],
    ['S7-06', '工程机械场景差异', 30, 'read', '差异清单'],
  ]},
  { id: 's8', title: '部署与运维', desc: 'Compose、systemd、网络、日志、bag 诊断、升级回滚', lessons: [
    ['S8-01', 'Docker Compose 编排', 35, 'teach', '一键起服务'],
    ['S8-02', 'systemd 服务化与开机自启', 35, 'teach', '服务单元'],
    ['S8-03', '网络、VPN 与远程接入', 35, 'teach', '接入方案'],
    ['S8-04', '日志体系与排障', 35, 'teach', '日志检索'],
    ['S8-05', 'rosbag 复盘诊断', 30, 'teach', '复盘报告'],
    ['S8-06', '远程升级与回滚', 35, 'teach', '回滚演练'],
    ['S8-07', '现场开机流程 SOP', 30, 'field', 'SOP 卡'],
  ]},
  { id: 's9', title: '业务专项复刻', desc: '远控全链路、Edge Bridge、配置、演示、验收', lessons: [
    ['S9-01', '远控全链路复盘', 40, 'teach', '全链路时序图'],
    ['S9-02', 'Edge Bridge 配置优先级', 35, 'teach', '配置覆盖实验'],
    ['S9-03', '激光 / IMU 配置与调参', 35, 'teach', '配置模板'],
    ['S9-04', '演示脚本编写', 30, 'teach', '5 分钟脚本'],
    ['S9-05', '验收检查点', 35, 'teach', '验收清单'],
    ['S9-06', '配置部署表解读（脱敏版）', 30, 'read', '字段说明'],
    ['S9-07', '演示前 72 小时清单', 30, 'field', '倒计时清单'],
  ]},
  { id: 's10', title: '全栈毕业项目', desc: '仿真挖机远控全链路 + 自动测试 + 验收报告', lessons: [
    ['S10-01', '项目拆解与验收标准', 30, 'teach', '任务分解'],
    ['S10-02', '虚拟 CAN + 执行器模型', 45, 'teach', '执行器仿真'],
    ['S10-03', '座舱指令与安全状态机', 45, 'teach', '指令链路'],
    ['S10-04', '标定与 TF 集成', 45, 'teach', '标定结果'],
    ['S10-05', '部署与故障演练', 45, 'teach', 'compose + 演练'],
    ['S10-06', '验收报告与答辩', 45, 'teach', '报告'],
  ]},
]

function yamlStr(s) {
  return JSON.stringify(s)
}

function skeleton(stage, [id, title, min, type, output]) {
  return `# ${id} · ${title}

> 本课为本阶段骨架占位，正文将在对应里程碑补全。当前可正常阅读、搜索、记笔记与做测验。

## 1. 现场类比

（待补：用一个现场场景解释本课要解决的问题。）

## 2. 核心概念

（待补：中英术语对照，配一张结构图或表格。）

## 3. 可复制命令 / 代码

\`\`\`bash
echo "TODO: ${id}"
\`\`\`

## 4. 动手实验

（待补：15–45 分钟内可完成的实验，含前置条件。）

## 5. 自动检查

（待补：检查脚本与通过判据。）

## 6. 常见故障

（待补：来自现场踩坑清单的症状 → 命令。）

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：${stage}
- 产出物：${output}

## 9. 下一节

—
`
}

let created = 0
let skipped = 0
for (const stage of stages) {
  const stageDir = path.join(base, stage.id)
  fs.mkdirSync(stageDir, { recursive: true })
  for (const lesson of stage.lessons) {
    const [id, title, min, type, output] = lesson
    const dir = path.join(stageDir, id.toLowerCase())
    fs.mkdirSync(dir, { recursive: true })
    const metaPath = path.join(dir, 'meta.yaml')
    const mdPath = path.join(dir, 'lesson.md')
    if (!fs.existsSync(metaPath)) {
      fs.writeFileSync(metaPath, `id: ${yamlStr(id)}
stage: ${yamlStr(stage.id)}
title: ${yamlStr(title)}
durationMin: ${min}
type: ${yamlStr(type)}
output: ${yamlStr(output)}
tags: []
sources: []
quiz: []
`, 'utf8')
      created++
    } else skipped++
    if (!fs.existsSync(mdPath)) {
      fs.writeFileSync(mdPath, skeleton(stage.id, lesson), 'utf8')
    }
  }
}
console.log(`scaffold done: meta created ${created}, existing ${skipped}, lessons ${stages.reduce((a, s) => a + s.lessons.length, 0)}`)
