# 持仓库迁移计划：positions.sqlite3 → Turso (libSQL)

**分支**：`feature/turso-positions-db`　|　**状态**：计划中（未实现）　|　**最后更新**：2026-06-20

---

## 1. 目标与动机

把**实时持仓监控库**从"二进制 SQLite 提交进 git"迁移到 **Turso（libSQL 托管）**，以彻底解决：

1. **git 二进制冲突**：本地（录入）与 GitHub Actions（写状态）同时提交同一个 `data/positions.sqlite3`，git 无法合并二进制 → 冲突 → 有丢数据风险（已实际发生）。
2. **多写入方并发**：UI 录入条款、Actions 写敲出状态——交给数据库做并发控制，而不是 git。
3. **commit 噪音**：Actions 每次回写都产生一次 commit。

**范围边界**：只迁移 `monitored_positions`（持仓库）。`research.sqlite3`（本地分析数据，已 gitignore）**保持本地 SQLite 不变**。

---

## 2. 设计决策（已定）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 托管 DB | **Turso (libSQL)** | SQLite 语义、现有 DBAPI 代码改动最小、免费档够用 |
| 连接方式 | **纯远程**（起步） | Actions/本地无需管理本地副本文件；低频访问够用 |
| 表结构 | **不拆表**，仍一张 `monitored_positions` | DB 自带并发控制，UI 写条款列、Actions 写状态列天然安全，无需拆表 |
| 本地兜底 | **保留**：未配 Turso 环境变量时回退本地 SQLite | 测试、离线开发照常；CI 不依赖网络 |
| research 库 | **不动** | 本地分析数据，与持仓无关 |

**写入方职责划分（逻辑层，非物理拆分）**：
- **条款（terms）**：UI（未来）/ `monitor_cli add` → `save_monitored_position`（写全部条款列）。
- **状态（state）**：GitHub Actions → `update_monitored_position_state`（**只**写 status / triggered_date / triggered_price / alert_sent_at / last_checked）。

---

## 3. 现状分析

- **访问层规整**：所有 DB 访问走标准 DBAPI `connection.execute(...)`，连接只在 `src/repository.py::connect()` 一处创建。
- **持仓库消费方**：仅 `src/monitor_cli.py`（`cmd_add` / `cmd_list` / `cmd_check`，3 处 `with connect(args.db)`）。
- **research 库消费方**：`src/analyze.py`（`--save-db`）——不在本次范围。
- **当前同步机制**：`.github/workflows/monitor-positions.yml` 跑完 `check` 后，把 `data/positions.sqlite3` `git add/commit/push`（第 65–77 行）——**这是冲突源，迁移后整段删除**。

---

## 4. 改动清单（逐文件）

### 4.1 `pyproject.toml`
- 新增依赖：`libsql-experimental`（SQLite 兼容 DBAPI 客户端）。

### 4.2 `src/repository.py`（核心）
- 新增持仓库专用连接工厂，例如 `connect_positions(db_path=None)`：
  - 若 `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` 存在 → 连 Turso（远程）。
  - 否则 → 回退本地 SQLite（默认 `data/positions.sqlite3`）。
- `connect()`（research 用）**保持不变**。
- **三个兼容性点**需在接入 Turso 时逐一验证（见 §8 待验证项）：
  1. `init_db` 用的 `executescript`（远程客户端可能需拆成单条 `execute`）。
  2. `with connect() as conn` 上下文管理器行为（提交/关闭语义）。
  3. 行的按名访问 `row["col"]`（sqlite3.Row 支持；libSQL 行需确认，必要时加薄适配层）。
  4. `cursor.lastrowid`（`save_monitored_position` 依赖）。

### 4.3 `src/monitor_cli.py`
- 持仓相关的 `with connect(args.db)` 改走 `connect_positions(...)`：配了 Turso 用远程，否则本地兜底。
- **顺带修误写地雷**：`--dry-run` 默认隐含 `--no-write`（避免"只想预览却改了库"的事故）；保留显式覆盖开关。

### 4.4 `.github/workflows/monitor-positions.yml`
- `env` 增加 `TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`（来自 repo Secrets）。
- **删除整段 "Commit status changes"（第 65–77 行）**：状态直接写 Turso，不再提交 sqlite。
- `--db data/positions.sqlite3` 去掉或保留为兜底参数。

### 4.5 `.gitignore` + 停止追踪
- 加入 `data/positions.sqlite3`，并执行 `git rm --cached data/positions.sqlite3`（数据不再进版本库）。

### 4.6 备份（补回 git 历史这一层）
- 新增 `monitor_cli export`（或 `dump`）：把 Turso 持仓导出为 JSON 快照。
- 可选：每周一个 workflow 把快照 commit 进 git 当冷备份（Turso 自身也有 backup）。

### 4.7 一次性迁移脚本
- 读现有 `positions.sqlite3` → 在 Turso 建表 + 灌数据。
- 迁移时**顺带核对**：id 11（新出口商单）、id 2 状态、以及之前提到的 strike 字段口径。

### 4.8 测试
- 本地 SQLite 兜底保证现有测试不依赖网络照跑。
- 新增"连接工厂选路"测试（mock 环境变量：有 Turso 变量走远程分支、无则本地）。

### 4.9 文档
- README / secrets 说明：本地 `.env` + GitHub Secrets 配置 Turso URL/token。

---

## 5. 你需要做的（Turso 侧，代码无法代办）

```bash
turso auth signup
turso db create fx-positions
turso db show fx-positions            # 取 Database URL
turso db tokens create fx-positions   # 取 auth token
```

把 **URL + token** 放进：
1. **GitHub repo Secrets**：`TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`。
2. **本地 `.env`**（不进 git）。

---

## 6. 落地顺序（分两阶段）

**阶段 A — 代码层（不依赖 Turso，现在就能写+测）**
1. `pyproject.toml` 加依赖。
2. `repository.py` 连接工厂 + 本地兜底。
3. `monitor_cli.py` 选路 + dry-run 修复。
4. 迁移脚本（读 sqlite 半段可测）。
5. 选路 + dry-run 测试。

**阶段 B — 上线（需 Turso 凭证）**
6. 接 Turso、验证 §8 兼容性点。
7. 跑迁移脚本灌数据。
8. 改 workflow（加 secrets + 删 commit 段）。
9. `.gitignore` + `git rm --cached` 停止追踪。
10. 加备份导出。

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| libSQL 客户端 API 与 sqlite3 有差异 | 连接工厂隔离 Turso 路径；必要时加薄适配层；§8 逐项验证 |
| 数据离开 git → 失去免费历史/备份 | §4.6 JSON 快照 + Turso 自带 backup |
| 网络依赖（Actions/UI 需连 Turso） | 低频访问；失败有日志；本地兜底用于开发/测试 |
| 凭证泄露 | 仅放 Secrets / `.env`；token 可随时轮换 |
| 迁移数据错漏 | 迁移后做一次行数 + 关键字段对账 |

---

## 8. 待验证项（接入 Turso 后确认）

- [ ] `libsql-experimental` 纯远程 `connect()` 的确切签名（`database=url, auth_token=...`）。
- [ ] 行能否按列名访问 `row["col"]`；否则加适配层。
- [ ] `executescript` 是否支持；否则拆单条 `execute`。
- [ ] `with conn` 上下文管理器与 `commit()` 语义。
- [ ] `cursor.lastrowid` 在远程下是否可用。

---

## 9. 不在本次范围

- research.sqlite3 的迁移（保持本地）。
- UI 本身（地基稳后另起）。
- 多人在线实时协作（当前定位"我 + 少数同事偶尔共享"）。
