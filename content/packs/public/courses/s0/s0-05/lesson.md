# S0-05 · Git：分支、回滚与现场版本管理

> 验证状态：✅ 分支、合并、`git reset --hard` 回滚已在 Ubuntu 24.04（WSL2，git 2.43）实测。

## 1. 现场类比

现场最常见的版本事故不是「代码写错」，而是：

- 在车上直接改配置，改坏了，**不知道改了什么**；
- 两个人同时动同一份参数表，**覆盖了对方的修改**；
- 回滚时只会把整个目录打包替换，**把现场标定数据一起冲掉**。

Git 解决的不是「多人协作」，首先解决的是**「我改了什么、什么时候能退回去」**。哪怕只有你一个人、哪怕只是配置文件，也值得用 Git 管起来。

## 2. 核心概念

### 2.1 三个区域

```
工作区 (working tree)  →  暂存区 (index)  →  本地仓库 (commit)
         git add                 git commit
```

- `git status`：随时看「哪些改了、哪些已暂存」；
- `git diff`：看**未暂存**的改动；
- `git diff --staged`：看**已暂存**的改动；
- `git log --oneline --graph`：看历史与分支结构。

### 2.2 分支与合并

- `git switch -c feature`：从当前点开新分支；
- `git merge feature`：把 feature 合回当前分支；
- 能快进（fast-forward）时不会产生合并提交；有分叉时产生 merge commit；
- 冲突时 Git 会在文件里写 `<<<<<<<` / `=======` / `>>>>>>>` 标记，**必须人工决定保留什么**。

### 2.3 回滚的三种力度（从轻到重）

| 命令 | 影响 | 何时用 |
|---|---|---|
| `git restore 文件` | 丢弃工作区未暂存改动 | 改错了还没 add |
| `git reset --soft HEAD~1` | 撤销提交，改动回到暂存区 | 提交信息写错/漏文件 |
| `git reset --hard HEAD~1` | **丢弃**提交及其改动 | 确认不要这次提交 |
| `git revert <commit>` | 生成一个反向提交 | 已经推送、别人可能拉取过 |

> ⚠ 高危：`reset --hard` 会丢工作区改动，执行前先 `git status` 确认没有未提交内容；不确定时先 `git stash`。

### 2.4 现场版本管理三条纪律

1. **每次上车改配置前先 commit**，哪怕只是 `checkpoint-<日期>`；
2. **标定数据不进同一个仓库**（体积大、含现场信息），单独备份并记录版本；
3. **发布给现场的版本打 tag**：`git tag v1.2.0-siteA`，回滚时按 tag 找回，不靠文件名记忆。

## 3. 可复制命令 / 代码

```bash
rm -rf /tmp/rl-s05 && mkdir -p /tmp/rl-s05 && cd /tmp/rl-s05
git init -q
git config user.email "learner@example.com"
git config user.name "learner"

echo "speed=1.0" > params.txt
git add params.txt && git commit -qm "init params"

git switch -c tune-speed
echo "speed=1.2" > params.txt
git commit -qam "tune speed to 1.2"

git switch -            # 回到原分支（通常 master/main）
git merge --no-edit tune-speed
git log --oneline --graph --all | head -n 5

git reset --hard HEAD~1 # 退回合并前，观察 params.txt 恢复 speed=1.0
cat params.txt
```

## 4. 动手实验

**目标（25 分钟）**：完整走一遍「建分支 → 改参数 → 合并 → 回滚 → 打 tag」。

1. 跑通上一节命令；
2. 再建一个分支，把 `speed` 改成 `1.5`，同时主分支改成 `1.1`，执行 `git merge` 制造一次冲突；
3. 手工解决冲突（保留你判断正确的值），`git add` 后 `git commit`；
4. 用 `git log --oneline --graph` 解释每条线是什么；
5. 打 tag：`git tag v1.0.0-learn`，用 `git tag -l` 确认。

**通过判据**：能说清 `reset --soft` 与 `reset --hard` 的差别，并知道已推送的提交该用 `revert`。

## 5. 自动检查

「实验」页签执行：

```bash
test -d /tmp/rl-s05/.git
git -C /tmp/rl-s05 log --oneline | grep -q "init params"
test "$(cat /tmp/rl-s05/params.txt)" = "speed=1.0"
```

## 6. 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| `fatal: not a git repository` | 不在仓库目录 | `cd` 到仓库根或 `git -C 路径` |
| 合并冲突不会退出 | 没解决完 | `git status` 看 `both modified` |
| `Your local changes would be overwritten` | 工作区有未提交改动 | 先 commit 或 stash |
| 提交里混入敏感文件 | 没写 `.gitignore` | 提交前 `git status` 复查 |
| 误提交后已推送 | 不能改写历史 | 用 `git revert` 而不是 reset |
| 大文件拖慢仓库 | 二进制/日志入库 | `.gitignore` + 必要时 `git lfs` |

## 7. 复盘题

见右侧测验面板（4 题）。

## 8. 关联资料

- 阶段：s0
- 来源：`E_ROS与Linux命令手册`
- 产出物：冲突解决演练记录（保留冲突片段与最终选择理由）

## 9. 下一节

S0-06 · Docker：镜像、容器、挂载、网络。
