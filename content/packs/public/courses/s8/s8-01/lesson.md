# S8-01 · Docker Compose 编排

> 验证状态：✅ 本课 compose 文件解析命令已在本机 Linux 实测（PyYAML）；⚠ 本机未安装 Docker，`docker compose up` 与容器间通信**未实测**。

## 1. 现场类比

一台设备上要跑：感知驱动、定位、控制桥、录像、Web 服务。有人用五个终端手工启动，顺序靠记，参数靠嘴传。

一次断电重启后，少起了一个容器，排查半小时。**编排的价值是：一条命令，确定的顺序，确定的配置。**

## 2. 核心概念

### 2.1 Compose 解决什么

| 问题 | Compose 的答案 |
|---|---|
| 启动顺序 | `depends_on` + 健康检查 |
| 网络互通 | 自定义网络 / host 模式 |
| 配置差异 | 环境变量、挂载配置文件 |
| 数据持久化 | volume / bind mount |
| 重启策略 | `restart: unless-stopped` |
| 多环境 | profiles、override 文件 |

### 2.2 一个服务的关键字段

| 字段 | 作用 | 现场注意 |
|---|---|---|
| `image` | 用哪个镜像 | 固定 tag，不用 `latest` |
| `command` | 覆盖启动命令 | 参数化，别写死现场值 |
| `environment` | 环境变量 | 不写明文密码/密钥 |
| `volumes` | 配置与数据 | 配置外挂，便于现场修改 |
| `network_mode` | 网络模式 | ROS2 DDS 常需 host 或正确多播 |
| `restart` | 重启策略 | 生产用 `unless-stopped` |
| `depends_on` | 启动依赖 | **只保证启动顺序，不保证就绪** |
| `healthcheck` | 就绪检测 | 配合 `condition: service_healthy` |

### 2.3 `depends_on` 的坑

```yaml
depends_on:
  - bridge
```

这只表示「先启动 bridge」，**不代表 bridge 已经能接收数据**。如果业务依赖「对方就绪」，必须加 healthcheck + `condition: service_healthy`，或在应用层重试。

### 2.4 ROS2 与容器网络

DDS 发现依赖多播/单播配置：

- 容器默认 bridge 网络下，多播经常不通；
- 简单做法：`network_mode: host`；
- 更规范：配置 `ROS_DOMAIN_ID`、`ROS_STATIC_PEERS`，开放必要端口；
- 无论哪种，**先在容器内验证「能看到对方话题」，再谈业务。**

### 2.5 配置管理原则

- 镜像只放代码，现场参数外挂；
- `.env` 不进镜像、不进仓库；
- 每个现场一份配置，带版本号；
- 启动前校验配置，出错就拒绝启动（与 S4-07 的驱动义务一致）。

## 3. 可复制命令 / 代码

```bash
# 生成并解析一个最小 compose 文件，检查服务名与重启策略
python3 -c "lines=['services:','  app:','    image: busybox','    restart: unless-stopped']; open('/tmp/c.yml','w').write(chr(10).join(lines)); import yaml; d=yaml.safe_load(open('/tmp/c.yml')); print(sorted(d['services']),d['services']['app']['restart'])"

# 有 Docker 的机器上（本机未实测）：
# docker compose config      # 校验并展开配置
# docker compose up -d       # 后台启动
# docker compose ps          # 查看状态
```

预期：`['app'] unless-stopped`。没有 Docker 时，至少先做静态校验，别把 YAML 错误带上现场。

## 4. 动手实验

**目标（35 分钟）**：写一份能「一条命令起来」的 compose 文件。

1. 列出需要运行的 3–5 个服务，标注依赖关系；
2. 为每个服务写 image（固定 tag）、command、volumes、restart；
3. 配置网络模式，说明 ROS2 发现如何工作；
4. 给关键服务加 healthcheck，并让依赖方等待 healthy；
5. 用本课命令做静态校验，再执行 `docker compose config`（有 Docker 时）；
6. 写结论：冷启动顺序是什么？哪个服务失败会阻塞全部？

**通过判据**：配置能通过 `docker compose config`；冷启动后所有服务 healthy；重启策略明确。

## 5. 自动检查

```bash
python3 -c "lines=['services:','  app:','    image: busybox','    restart: unless-stopped']; open('/tmp/c.yml','w').write(chr(10).join(lines)); import yaml; d=yaml.safe_load(open('/tmp/c.yml')); assert d['services']['app']['restart']=='unless-stopped'; print('COMPOSE_OK')"
```

预期输出 `COMPOSE_OK`。

## 6. 常见故障

| 症状 | 可能原因 | 排查 |
|---|---|---|
| 一条命令起不来 | YAML 缩进错、字段名错 | `docker compose config` |
| 依赖服务还没就绪就报错 | 只写了 `depends_on` | 加 healthcheck + condition |
| 容器间看不到话题 | 网络模式/多播/domain id | 进容器 `ros2 topic list` 对比 |
| 重启后数据丢了 | 没挂 volume | 数据目录外挂 |
| 改了配置不生效 | 配置被打进镜像或缓存 | 外挂配置 + 重启服务 |
| 密码出现在镜像里 | 环境变量写死 | 用 secrets/外部注入 |
| 现场能跑、换机器不行 | 镜像 tag 不固定 | 固定版本并留归档 |

## 7. 复盘题

见右侧测验面板（3 题）。

## 8. 关联资料

- 阶段：s8
- 来源：`06_软件部署与运维`、`E_ROS与Linux命令手册`
- 产出物：compose 文件 + 启动顺序说明

## 9. 下一节

S8-02 · systemd 服务化与开机自启：让服务在断电重启后自己站起来。
