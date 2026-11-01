# ADR-001 · 三端技术选型

状态：已采纳（2026-11-02）

## 决策

采用 **React + TypeScript + Vite 共享前端 + Electron 桌面壳 + Capacitor 移动壳**，不采用 Tauri 2。

```
packages/core     内容解析 / 搜索 / 进度 / 测验 / 同步（纯 TS，无平台 API）
apps/web          共享界面（唯一 UI 实现）
apps/desktop      Electron 主进程 + 本地实验适配 + electron-builder
apps/mobile       Capacitor 壳 + Android 原生能力
content/packs     public（内置）/ private（用户导入，不入仓库）
```

## 理由

1. **三端同源最彻底**：Electron 与 Capacitor 都加载同一个 `apps/web/dist`，不存在第二套 UI 代码。Tauri 的移动端与桌面端 UI 虽同源，但打包链更分散。
2. **deb / exe / apk 三产物路径成熟**：electron-builder 直接产出 NSIS 与 deb；Capacitor 直接产出签名 apk。Tauri 2 的 Android 打包依赖 Rust + NDK + 交叉工具链，在 Windows 主机上失败面更大。
3. **团队可维护性**：全部为 JS/TS，无 Rust 编译等待；课程系统的主要复杂度在内容与状态，不在壳。
4. **离线能力**：Electron 主进程可访问文件系统做内容包导入、本地实验执行、调用 `wsl.exe`；Capacitor 提供 SAF 文件选择、SQLite、分享。
5. **体积可接受**：Electron 安装包约 80–120 MB，对桌面无压力；apk 端 WebView 复用系统内核，包体约 6–10 MB。

## 代价与缓解

| 代价 | 缓解 |
|---|---|
| Electron 包体大、内存占用高 | 只开一个窗口；课件资源分离加载；不内嵌视频 |
| 移动端 WebView 性能与 API 差异 | 所有平台差异收敛到 `core/platform` 适配层；三端冒烟测试必跑 |
| Electron 在 Linux 上构建 deb 需在 Linux 环境 | 在 WSL Ubuntu 24.04 内复用同一脚本构建；Makefile 统一入口 |
| 原生 SQLite 插件跨端安装复杂 | 统一用 IndexedDB（`idb`）+ JSON 导出；满足「可导出同步」硬要求 |

## 备选方案评估

| 方案 | 通过 | 淘汰原因 |
|---|---|---|
| Tauri 2 | 部分 | 需 Rust 工具链；Windows 构建 Android 需完整 NDK 链路；与「先用三个空壳包冒烟」的节奏冲突 |
| Flutter | 否 | 与 Markdown/Shiki/KaTeX 生态不匹配，重写渲染层成本高 |
| 纯 Web + PWA | 否 | 无法满足 deb/exe 安装包硬要求 |
| React Native | 否 | 三端 WebView 方案已足够，RN 增加分叉 |

## 风险

1. Capacitor Android 构建依赖本机 SDK/Gradle；已确认 `D:\Private data\AI\Tools` 下有 JDK17、android-sdk、gradle-8.9。
2. Electron 首次安装需下载约 100 MB 二进制；已配置镜像回退策略，失败时记录为环境阻塞项，不伪造产物。
3. 三端 WebView 内核版本不同（Windows WebView2 / Android System WebView / Chromium）→ CSS 只用广泛支持特性，禁用新语法。

## 约束

- 共享代码优先：`apps/web` 与 `packages/core` 不允许出现 `if (platform === ...)` 之外的分叉。
- 平台适配集中在 `packages/core/src/platform/`：`fs`、`pickFile`、`runExperiment`、`share`。
- 任何一端不得出现「功能缺失」，只能出现「后端不可用，进入只读/步骤模式」。
