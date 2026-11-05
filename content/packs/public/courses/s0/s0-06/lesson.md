# S0-06 · Docker：镜像、容器、挂载、网络

> 验证状态：✅ 2026-11-04 在 WSL2 Ubuntu 24.04 的 Docker 引擎实测：`docker --version`、`docker info`、`docker run --rm hello-world` 与 `docker image inspect hello-world` 均通过（需本机已有 `hello-world` 镜像）。没有 Docker 时，应用会显示「当前设备没有可用的 Linux 后端」，不会伪造结果。

## 1. 现场类比

「我电脑上能跑，车上跑不起来」的根源通常是环境差异：glibc 版本、Python 依赖、ROS 发行版。Docker 把这套环境**连操作系统用户态一起打包**，让「能跑」变成可复制的事实。

对交付工程师的意义：你可以把 ROS1（Ubuntu 20.04）和 ROS2（Ubuntu 22.04/24.04）跑在同一台 24.04 机器上，不用来回重装系统。

## 2. 核心概念

### 2.1 镜像、容器、仓库

| 名词 | 类比 | 特点 |
|---|---|---|
| 镜像 image | 安装光盘 | 只读、分层、可复用 |
| 容器 container | 用光盘装出来的一台虚拟机 | 有独立进程/网络/文件系统，但共享内核 |
| 仓库 registry | 光盘商店 | Docker Hub、私有 registry |

**容器不是虚拟机**：没有自己的内核，所以启动是秒级，也不能装不同版本的内核模块。

### 2.2 四个必会操作

```bash
docker pull ros:humble-ros-base           # 拉镜像
docker run --rm -it ros:humble-ros-base bash   # 起临时容器
docker ps -a                              # 看所有容器
docker images                             # 看本地镜像
```

`--rm` 退出即删；`-it` 交互终端；`-d` 后台；`--name` 命名。

### 2.3 挂载与网络

```bash
# 把宿主机当前目录挂到容器 /work；容器内改动会落到宿主机
docker run --rm -it -v "$PWD:/work" -w /work ubuntu:24.04 bash

# 端口映射：宿主机 8080 → 容器 80
docker run --rm -d -p 8080:80 nginx:alpine

# 容器与宿主机共享网络（ROS2 DDS 调试常用）
docker run --rm -it --network host ros:humble-ros-base bash
```

> ⚠ 注意：`--network host` 只在 Linux 上等价于宿主机网络；Docker Desktop（Windows/macOS）行为不同。

### 2.4 安装（Ubuntu 22.04 / 24.04）

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"   # 重新登录后生效
```

若处于内网，需按公司镜像源要求替换 `download.docker.com` 与 Docker Hub 地址（此处不提供具体内网地址）。

## 3. 可复制命令 / 代码

```bash
docker --version
docker run --rm hello-world
docker info --format '{{.ServerVersion}}'
docker run --rm -v "$PWD:/work" -w /work ubuntu:24.04 bash -lc 'pwd && ls -la | head'
```

预期：`hello-world` 打印成功信息；`docker info` 输出服务端版本号。

## 4. 动手实验

**目标（30 分钟）**：在一台有 Docker 的 Linux 机器上跑通 ROS2 容器。

1. 安装 Docker（见 2.4），确认 `docker run --rm hello-world` 成功；
2. `docker pull ros:humble-ros-base`；
3. 启动交互容器：`docker run --rm -it ros:humble-ros-base bash`；
4. 容器内执行 `source /opt/ros/humble/setup.bash && ros2 doctor --report | head`；
5. 退出容器，执行 `docker ps -a` 确认临时容器已删除（`--rm` 生效）。

**通过判据**：能解释「容器里的 ROS 版本与宿主机发行版为什么可以不同」。

## 5. 自动检查

「实验」页签执行：

```bash
docker info --format '{{.ServerVersion}}'
docker run --rm hello-world
```

没有 Docker 时两条都会失败并显示「当前设备没有可用的 Linux 后端」或 `docker: command not found`——**这是预期行为**，不是课程错误。

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `permission denied /var/run/docker.sock` | 用户不在 docker 组 | `sudo usermod -aG docker $USER` 后重新登录 |
| `Cannot connect to the Docker daemon` | 服务没起 | `sudo systemctl status docker` |
| 拉镜像超时 | 网络/镜像源 | 配置私有 registry 或代理 |
| 容器内改的文件重启丢失 | 没挂载卷 | `-v 宿主机目录:容器目录` |
| 端口冲突 | 宿主机端口已占用 | `ss -tlnp` 查占用后换端口 |
| 磁盘被镜像占满 | 旧镜像/停止容器堆积 | `docker system df`、`docker system prune`（确认后再执行） |

> ⚠ 冲突提示：网上教程常用 `docker run -v /var/run/docker.sock` 或 `--privileged`，这会显著扩大权限。课程实验**不需要**，现场使用前必须评估安全边界。

## 7. 复盘题

见右侧测验面板（4 题）。

## 8. 关联资料

- 阶段：s0
- 来源：`E_ROS与Linux命令手册`
- 产出物：ROS 容器跑通记录（镜像名、版本、`ros2 doctor` 输出摘要）

## 9. 下一节

S0-07 · 机器人四层架构与数据流：把 S0-01 的图落到可排查的模块。
