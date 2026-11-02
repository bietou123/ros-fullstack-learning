# 工业机器人全栈学习系统

[![verify](https://github.com/bietou123/ros-fullstack-learning/actions/workflows/verify.yml/badge.svg)](https://github.com/bietou123/ros-fullstack-learning/actions/workflows/verify.yml)

面向工业机器人（含工程机械远控）交付工程师的离线全栈学习系统。同一套 React 前端与同一份内容包，构建为 Windows 桌面端、Linux 桌面端和 Android 平板端三个产物；学习功能完全一致，仅实验执行后端按平台适配。

- 课程：S0–S10 共 11 个阶段、76 节课，每节 25–45 分钟
- 每节课固定 9 段：现场类比 → 核心概念 → 可复制命令 → 动手实验 → 自动检查 → 常见故障 → 复盘题 → 关联资料 → 下一节
- 功能：目录/正文/代码高亮/KaTeX、全文搜索、阅读进度、笔记、书签、测验、错题复习（SM-2）、学习数据导入导出
- 离线优先：内容随安装包内置，不依赖网络与收费服务

## 三端产物

| 平台 | 产物 | 实验后端 |
|---|---|---|
| Windows 10/11 | NSIS 安装包 `.exe` | WSL2（`wsl.exe`）；不可用时明确显示只读模式 |
| Linux x86_64 / arm64 | Debian 安装包 `.deb` | 本机 Shell；声明了 `image` 的实验走 Docker |
| Android 8+（arm64） | 签名 `.apk` | 未接入 SSH；无后端时只读展示实验步骤与检查项 |

实验每个命令独立执行，结果实时回传；没有可用后端时返回 `no-backend` 或 `failed`，**不会伪造实验成功**。硬件、ROS、Docker 相关步骤若未在对应环境实测，课程中会标注「⚠ 未实测」。

## 快速开始（开发）

要求：Node.js 20+（推荐 22/24）、pnpm 10.33（仓库已固定 `packageManager`）。

```bash
corepack enable
pnpm install
pnpm build          # 构建内容包 + 前端
pnpm dev            # 浏览器开发模式
```

常用命令：

| 命令 | 说明 |
|---|---|
| `pnpm typecheck` | 核心包与前端类型检查 |
| `pnpm test` | 核心库单元测试（Node 内置 test runner） |
| `pnpm verify` | 内容包哈希、课程结构、覆盖率、敏感信息扫描；首次运行会自动生成内容包 |
| `pnpm verify:release` | 从 `release/` 的 exe/deb/apk 中抽取内容包，比对哈希、课程结构与正文（exe 解包需 7-Zip，缺失时跳过） |
| `pnpm verify --full` | 追加类型检查、单测和前端构建 |
| `pnpm package:exe` | 构建 Windows NSIS 安装包 |
| `pnpm package:deb` | 构建 Linux deb（需 Linux/WSL，含 x64/arm64） |
| `pnpm package:apk` | 构建签名 Android APK（需 JDK 17 + Android SDK） |
| `pnpm smoke:desktop` | 构建并运行桌面端隐藏窗口冒烟；前缀 `RL_SMOKE_OFFLINE=1` 可强制断网并校验测验 |
| `make verify` / `make package-exe` | 同上，命令行别名 |

产物统一写入 `release/`。打包脚本会依次执行内容构建、敏感信息扫描和严格校验，任一步失败即中止。

GitHub Actions 的 `verify-release` 工作流会在 Release 发布后自动下载已上传的 exe/deb/apk，复跑 `pnpm verify:release`；也可手动触发：`gh workflow run verify-release.yml -f tag=v0.1.0 -f ref=main`。

## 构建三端

### Windows exe

```bash
pnpm package:exe
# release/IndustryRoboticsLearning-<version>-x64.exe
```

### Linux deb

在 Ubuntu/WSL 中执行（需要 Node、pnpm、electron-builder 依赖）：

```bash
pnpm package:deb
# release/ros-fullstack-learning_<version>_amd64.deb
# release/ros-fullstack-learning_<version>_arm64.deb
```

若在 Windows 上通过 WSL 打包，建议把源码同步到 WSL 内再安装依赖，避免把 Windows 的 `node_modules` 带到 Linux（否则会缺 `@rollup/rollup-linux-*` 等原生包）。

### Android apk

需要 JDK 17 与 Android SDK（`ANDROID_HOME` 或 `apps/mobile/android/local.properties` 的 `sdk.dir`，路径使用正斜杠）。

```bash
pnpm package:apk
# release/IndustryRoboticsLearning-<version>-arm64.apk
```

签名读取仓库根 `.signing/keystore.properties`（已被 `.gitignore` 排除）。未提供签名材料时 Gradle 只产出未签名包，`package:apk` 会因找不到 `app-release.apk` 而失败，不会误发 debug 包。

## 内容包

- 源码：`content/packs/public/`（`manifest.json`、`courses/**/meta.yaml`、`lesson.md`、`glossary.json`）
- 构建：`scripts/build-pack.mjs` 生成 `apps/web/public/content/pack.json` 与 `build-info.json`
- 哈希：`sha256(JSON.stringify({ manifest, stages, lessons, glossary }))`，其中 manifest 只取 `id/name/version/visibility/minAppVersion/license/description`，构建时间与计数不参与
- 三端加载同一份 `pack.json`；设置页展示应用版本、内容版本与哈希

私有内容包（公司内部资料）通过设置页以 `.json` / `.zip` 导入，只保存在本机 IndexedDB，**不会进入任何公开产物或 Git 仓库**。

`scripts/verify.mjs` 会检查：内容包哈希自洽、76 节/11 阶段、每节课结构、id 唯一与阶段顺序、资料覆盖映射、敏感信息。`--strict` 会把骨架课程判为失败。

## 目录结构

```
apps/web          React 前端（三端共享）
apps/desktop      Electron 主进程 / 预加载 / 打包配置
apps/mobile       Capacitor 壳与 Android 工程
packages/core     内容包、搜索、测验/SM-2、IndexedDB、平台适配
content/packs     内容包（public 随包发布；private 永不提交）
scripts           构建、打包、校验、敏感扫描、图标生成
docs              资料盘点、能力矩阵、课程地图、ADR、里程碑、冒烟/验收报告
```

## 数据与隐私

- 学习进度、笔记、书签、测验记录只存本机 IndexedDB
- 设置页支持全量 JSON 导出/导入，换设备可迁移；桌面端直接下载文件，Android 端通过系统分享面板保存或发送
- 仓库与安装包在构建前执行敏感信息扫描；公开内容全部脱敏，不含真实 IP、序列号、客户信息、报价或明文凭据
- 公司内部课程只能作为私有内容包导入，禁止提交公开仓库或打入公开安装包

## 已知限制

- arm64 deb 尚无对应硬件实机验证；Android APK 已签名并校验内容哈希，并在 Android 34 x86_64 无窗口模拟器上完成启动、离线学习、进度落盘与数据导出/导入验证，但**未做 Android 真机启动验证**
- Android 学习数据导出依赖系统分享面板（`@capacitor/filesystem` + `@capacitor/share`）；v0.1.0 发布版 APK 早于该修复，需重新构建发布
- 依赖实车、真实 ROS 发行版、Docker 镜像或硬件的实验命令，课程内均标注「⚠ 未实测」；合成数据的自动检查可离线复现
- 课程来源映射分两层：`docs/coverage.csv` 记录每份内部资料的直接归属，`docs/lesson-sources.csv` 记录每节课 `meta.yaml` 声明的来源；`pnpm verify` 要求 76/76 节均有可解析来源，但部分课程只到章级/通用手册，未逐文件对应到具体文档
- Windows 安装包未做代码签名，首次运行可能出现 SmartScreen 提示

## 许可

代码与示例采用 MIT；课程文本采用 CC BY 4.0。详见 [LICENSE](LICENSE)。
