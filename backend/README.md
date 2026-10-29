# 禾观 AgriScan API

Python 3.12 + FastAPI + SQLAlchemy。前端和 API 在 Windows 本机运行，Docker Compose 仅运行 MySQL、Redis，不构建前后端应用镜像。

在**项目根目录**首次执行：

```powershell
.\scripts\start-dev.ps1 -Install
```

脚本使用 `backend/.venv` 安装基础、推理和存在时的 `requirements-media.txt` 媒体依赖，并安装前端 npm 依赖；日常启动省略 `-Install`。需要 Node.js 22.12+、Python 3.12+、Docker Desktop Linux 容器。应用配置保存在 `backend/.env`，根 `.env` 仅保存 Docker 数据库参数；已有文件、账户及密钥不会被脚本覆盖。

- 工作台：[http://localhost:5173](http://localhost:5173)
- 管理端：[http://localhost:5173/#admin/overview](http://localhost:5173/#admin/overview)
- API：[http://localhost:18000/docs](http://localhost:18000/docs)
- 健康：[http://localhost:18000/api/health](http://localhost:18000/api/health)
- MySQL：本机 `13308` → 容器 `3306`；Redis：本机 `16380` → 容器 `6379`。

`backend/.env` 中的 `DATABASE_URL` 使用 `mysql+pymysql://…@127.0.0.1:13308/…`，`REDIS_URL` 使用 `redis://127.0.0.1:16380/0`。数据库名称、用户及密码需匹配根配置。上传目录为本机 `backend/uploads/`，模型清单使用主机路径。API 默认 `18000`，支持启动参数 `-ApiPort`；Vite 默认 `5173`，支持 `-WebPort`。脚本只在启动 Vite 时临时设置 `AGRISCAN_API_TARGET`，退出脚本时恢复原环境变量，不修改后端配置。

前端源码热更新，后端和应用配置变化需重启。停止使用根目录 `scripts/stop-dev.ps1`：安全停止本项目原生会话，再停两个数据库容器，保留卷和本机上传文件。只停应用可用 `-NativeOnly`。日志在根 `.logs/`，不再使用 API/前端容器日志。

全新模板账号 `admin / admin12345`；已有环境使用 `backend/.env` 的账户。演示模式只公开普通只读业务，管理接口始终需管理员；正式模式图片通过带凭证 fetch 读取。

## 已实现

- JSON 登录、JWT 会话、获取当前用户、令牌注销与持久化吊销记录；密码 PBKDF2 哈希存储，密码轮换自动使旧 JWT 失效。
- 数据看板：数据库真实聚合，7 / 30 天趋势，Redis 30 秒缓存，写操作清理缓存。
- 检测记录：图片上传、筛选、详情、删除。图片必须可解码为 JPEG/PNG/WebP，限制 10 MB / 2500 万像素；解码后重新编码，移除元信息，随机文件名持久化。
- 地块管理：新增、修改、删除、实景封面和地图定位。删除地块保留历史检测并解除关联；存在关联检测的地块不可变更作物。
- 模型管理状态、作物支持列表、数据库知识库与发布流程。知识库为一般性巡检提示，不能代替农技人员的现场判断。
- 明确标记 `is_demo=true` 的历史演示数据，首次启动仅初始化一次。真实上传 `is_demo=false`，不会产生虚构推理结果。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 数据库 / Redis / 模型状态 |
| POST | `/api/auth/login` | JSON `{username, password}` |
| GET | `/api/auth/me` | 当前用户 |
| POST | `/api/auth/logout` | 吊销当前 JWT |
| GET | `/api/dashboard?days=7` | `days` 支持 7 或 30；卡片为累计数量 |
| GET | `/api/detections?search=&crop=&status=` | 记录列表 |
| POST | `/api/detections` | multipart: `file, crop?, plot_id?, note?`；省略或留空 `crop` 自动识别作物 |
| GET / DELETE | `/api/detections/{id}` | 查询 / 删除检测 |
| GET | `/api/uploads/{filename}` | 查询已入库图片 |
| GET / POST | `/api/plots` | 地块列表 / 创建 |
| PATCH / DELETE | `/api/plots/{id}` | 修改 / 删除 |
| POST | `/api/plots/{id}/cover` | 管理员上传封面；multipart: `file` |
| DELETE | `/api/plots/{id}/cover` | 管理员移除封面；已有地块无封面时重复调用仍成功，返回更新后的地块 |
| GET | `/api/models` | 模型接入状态 |
| GET | `/api/knowledge` | 知识库 |

模型置信度字段范围为 0–1；地块 `health_score` 为已完成检测中健康结果的百分比（0–100），无已完成检测则为 null。`stats.pending` 包含等待模型、排队和处理中；失败记录只计入总数。

模型就绪时，上传检测可以省略 `crop`，由全类别 Top-1 同时确定作物及病害或健康状态；响应和记录的 `crop` 保存识别出的作物，候选分数不按浏览主题筛选或归一化。低置信度结果标为需关注并提示复核。指定地块与识别作物不一致时返回 422、提示取消或更换关联，不保存记录并清理临时图。显式传入作物的旧接口继续验证所选作物；未配置模型时自动识别返回明确的 422，手动指定作物仍可采集待检测样本。

地块创建、修改支持可选的 `latitude`、`longitude`（WGS84），必须成对提交，同时为 null 时清除标记。地块列表返回 `cover_url` 和坐标；未设置时为 null。封面沿用图片格式、大小及像素校验，最长边缩至 1600 像素后保存为 JPEG，替换、移除封面或删除地块时清理旧封面。封面操作独立于地块信息保存，上传失败可重试而不重复创建地块。前端删除已有封面时先保存待删除草稿标记，可撤销，点击“保存地块”后才调用删除接口；该接口仅管理员可用，对已有地块的重复删除封面请求保持幂等，地块不存在时返回 404。

旧图片在数据库引用更新后再清理。Windows 文件占用等原因可能使无引用文件暂留磁盘，清理失败会记录日志，不影响已经提交的地块结果；`/api/uploads/{filename}` 校验数据库引用，因此旧图片即使暂留磁盘也会返回 404。

封面与坐标保存在新增的 `plot_details` 关联表，原有 `plots` 表不变。应用启动时通过 Alembic 版本迁移创建此新表，保留原有地块数据。前端地图采用 Leaflet 和 OpenStreetMap，底图依赖联网；底图不可用时仍可填写经纬度。

## 训练权重接入

`app/inference.py` 定义 `InferenceProvider` 接口和 `InferenceResult`，包含 `OnnxClassificationProvider` 与 `AwaitingWeightsProvider`。仓库附带经过验证的 PlantVillage 发布模型，覆盖 14 种作物、38 个类别，属于单叶图像的单标签分类，不输出病斑框，也不能据此判断多病共存。

根启动脚本 `-Install` 安装 `requirements-inference.txt`。在 `backend/.env` 设置本机相对路径 `MODEL_MANIFEST=../models/releases/plantvillage-yolo26m-906cf72f6bf0/manifest.json`，取得 Git LFS 实际模型后重启本机 API。启动时校验清单、类别、预处理、输入输出形状及模型 SHA256；`/api/health` 中 `model: ready` 表示模型已加载。详细说明见[模型文件说明](../models/README.md)及[训练与接入说明](../training/README.md)。

未配置 `MODEL_MANIFEST` 时使用 `AwaitingWeightsProvider`，手动指定作物采集图片后标为 `awaiting_model`，`result` 和 `confidence` 均为 null；自动识别请求返回明确错误。配置的模型无法通过加载校验时，服务启动失败，需要修正配置。模型管理页上传的权重仅登记保存，不自动反序列化、加载或执行。

当前推理在 API 进程中执行，Redis 仍用于看板缓存，尚未运行推理队列或独立 worker。其他权重需要按实际任务适配 provider、明确类别映射与预处理，并通过独立验证后显式启用；队列、模型版本切换等能力仍需后续实现。

## 部署与数据

根 `.env` 保存 Docker 数据库参数；`backend/.env.example` 列出本机 API 配置，实际配置保存在 `backend/.env`。`DEMO_MODE=false` 会拒绝默认密码、短 JWT 密钥、SQLite 和空 Redis URL。MySQL 和 Redis 的完整环境由仓库根目录 Compose 提供。

应用首次启动通过版本迁移建表并建立由环境变量管理的管理员。每次启动都会将此账号的用户名和密码同步到 `ADMIN_USERNAME` / `ADMIN_PASSWORD`；修改这些变量并重启即可轮换凭证，旧密码和旧 JWT 随即失效。管理员身份 ID 保留，改用户名不会残留另一个演示管理员。请在各实例使用同一套凭证配置，避免启动时相互覆盖。生产模式拒绝两个内置示例 JWT 密钥；发现其他仍使用演示密码的旧账号会拒绝启动，需先重置或移除。

后续表结构变更通过 `alembic/versions/` 中的显式修订管理，应用启动时升级到当前版本。首次生产部署应使用独立空数据库，不要复用演示数据库；切换 `DEMO_MODE` 不会删除已有数据。`uploads/` 和数据库必须一起备份。

Redis 故障会令健康状态显示 `degraded`，业务仍可直接读写数据库。缓存失效失败时旧数据最多保留 30 秒。当前登录频率限制为单进程内的每来源地址 / 用户组合 5 分钟最多 10 次失败；多实例生产部署需在网关增加统一限流。

检测与地块按 `owner_id` 隔离。每个登录账户只能在个人接口读取、统计和管理自己的数据；管理员在个人用户端同样受归属限制，仅独立 `/api/admin/*` 管理接口可跨用户维护。普通成员可以创建自己的地块、上传检测、删除自己的样本并使用私人对话；知识库、推理模型和平台运行配置仍由管理员维护。未知历史归属保留为 NULL，只在管理端待分配列表可见，不自动认领。可通过 `REGISTRATION_ENABLED=false` 关闭注册，注册流程支持可配置的邮箱验证。详见[用户数据隔离验收](../docs/user-isolation-20261029.md)。

自动化测试使用独立数据库，不应直接对日常 MySQL 业务库运行。在 `backend/` 中执行 `.\.venv\Scripts\python.exe -m pytest -q --basetemp=../.runtime/pytest`，避免本机系统临时目录权限影响测试。


## 管理端与数据库升级

本地入口为 [http://localhost:5173/#admin/overview](http://localhost:5173/#admin/overview)，使用原管理员账户登录，也可以从工作台左侧进入「管理中心」。普通成员不能访问管理接口，演示模式也不例外。

- 概览：真实数据库计数、7/30 天检测趋势和最近管理操作；日期使用中国时区。
- 用户：分页搜索、新建、资料和邮箱维护、角色变更、启用/停用、密码重置。保留初始化管理员与当前管理员的管理入口；用户停用、角色变更及密码重置会撤销旧会话。
- 地块：复用现有封面、坐标、草稿和增删改；管理列表支持分页筛选。
- 检测：分页、作物/状态/来源/地块/日期筛选；只可编辑名称、备注和地块，原分类结果及模型快照不可改写。CSV 导出全部筛选结果，最多 10,000 条，带 UTF-8 BOM 及公式前缀防护。
- 知识：数据库维护草稿、发布、归档及参考来源。普通知识库只读取已发布条目，正文按纯文本显示。上传权重仍只登记，不自动执行或启用未经验证的文件。
- 日志：管理变更与审计同事务保存，记录操作人、资源、动作和时间，不保存密码或接口密钥；管理员不能通过此入口读取其他账号私人对话。

新增持久表为 `knowledge_articles`、`audit_logs`，用户表增加 `is_active`、`token_version`、`created_at`、`updated_at`。旧账号未采集的注册时间保持空值，新增账号自动记录；首次更新旧令牌会失效，需要重新登录。

应用启动自动执行迁移，保留原检测、地块、账户、上传文件和模型快照。旧 SQLite 库首次升级前会创建数据库同级 `backups/<数据库名>-before-admin-<UTC时间>.sqlite3` 备份；备份包含账号和业务数据，应与数据库一起受控保存。MySQL 迁移使用连接级锁；升级前由运维备份数据库和上传文件。初始修订禁止自动破坏性降级，回退需恢复匹配版本的备份。

API 启动自动执行同一备份与加锁迁移入口。升级前备份数据库与本机上传文件；修改后端后重启，依赖变化加 `-Install`。直接 Alembic CLI 不经过应用备份入口，不应绕过备份、连接锁与停写步骤。

旧 SQLite 与宿主机上传目录不会被 MySQL 自动读取。跨库迁移需要专用导入流程，在源服务停写和备份后同时处理关联业务数据与文件，并核对数量、图片可读性；保留原库和上传文件。数据导入与 Alembic 表结构升级是两个步骤。

本机 API 日志在根 `.logs/api.out.log`、`.logs/api.err.log`；数据库日志使用 `docker compose -p agriscan logs -f mysql redis`。停止两个数据库保留命名卷。

2026-10-28 最终本地验证：后端全套 155 项测试通过，1 项因 Windows 符号链接权限跳过；前端 TypeScript 与 Vite 构建通过。覆盖历史 SQLite 升级与安全导入、MySQL 时间及浮点精度、权限与会话、知识可见性、分页导出及现有业务回归。本机实际启动 API 使用 `-ApiPort 18001`，Vite 代理已同步；MySQL、Redis、ONNX 模型及管理员页面均验证就绪，9 个原有图片引用可读取，20 条检测完整导出，6 段私人对话保留。另外在独立 MySQL 8.4 临时容器验证了旧用户表升级、原账号登录、趋势聚合、中文长正文、知识发布、CSV 与审计；测试容器已清理。

## 旧 SQLite 安全导入

当前已完成迁移的 MySQL 不需要再执行本节。导入前必须停止本机后端写入，并准备独立空目标库；不要先启动 API，以免演示初始化向空库写入数据。工具只读取源备份，不升级或覆盖原 SQLite，拒绝非空目标和同名不同内容文件。

1. 确认本机虚拟环境已安装依赖，`backend/.env` 指向准备好的空 MySQL 数据库，`UPLOAD_DIR` 指向本机目标上传目录。只启动数据库：

```powershell
.\scripts\stop-dev.ps1 -NativeOnly
docker compose -p agriscan up -d --wait mysql redis
```

2. 在项目根目录创建独立备份。下面使用 SQLite backup API，包含 WAL 中已经提交的数据；上传文件另行复制。源数据库路径如与示例不同需相应调整：

```powershell
$legacyBackup = Join-Path (Get-Location) (".runtime/legacy-import-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $legacyBackup | Out-Null
.\backend\.venv\Scripts\python.exe -c "import sqlite3,sys; source=sqlite3.connect('file:backend/data/agriscan.db?mode=ro',uri=True); target=sqlite3.connect(sys.argv[1]); source.backup(target); target.close(); source.close()" (Join-Path $legacyBackup "agriscan.sqlite3")
if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed; import was not started." }
Copy-Item -LiteralPath backend/uploads -Destination (Join-Path $legacyBackup "uploads") -Recurse
```

3. 从 `backend/` 执行专用 CLI，目标连接和上传目录从 `backend/.env` 读取。源上传备份和目标上传目录必须相互独立：

```powershell
Push-Location backend
try {
    .\.venv\Scripts\python.exe -m app.import_legacy --source (Join-Path $legacyBackup "agriscan.sqlite3") --uploads (Join-Path $legacyBackup "uploads")
    if ($LASTEXITCODE -ne 0) { throw "Import failed; retain the backup and inspect the reported error." }
} finally { Pop-Location }
```

工具支持结构完整、版本为 `20261028_02` 至 `20261029_06` 的源库；旧版本没有归属列时保留为 NULL，06 已有归属时原样保留。02/03/04 源库尚无运行配置表时，目标会创建空配置表并使用环境默认值，原库保持只读。版本更早时先按原系统升级流程处理，再重新备份。成功时报告各表行数与引用文件数量；失败时保留源备份并回滚未提交的目标数据。随后运行 `scripts/start-dev.ps1`，核对登录、地块、检测、私有聊天、知识与图片。

05 源库中的接入密钥以密文原样迁移。对应的 `CONFIG_ENCRYPTION_KEY` 必须通过独立安全渠道迁至目标运行环境；数据库、上传文件或分享包中不得附带 `.env` 或明文密钥。缺失或错误的解密密钥会让 API 在启动时报告可诊断错误，不会清空旧配置或静默回退。

本次已验证迁移：1 个账户、3 个地块、20 条检测、6 段对话、12 条消息、4 篇知识及 9 个引用文件。迁移后逐行核对 15 张业务表（另含 1 张迁移版本表）、14 个时间列与文件 SHA256，并保留源备份；MySQL 时间精度和历史置信度/面积精度由显式修订维护。

## 后台图片与视频任务

`/api/detection-tasks` 提供当前登录会话内的后台上传任务：先以 JSON `POST` 预留（`client_request_id` 为 UUID），再 `PUT /{id}/file` 上传原始文件；`GET` 列表或 `GET /{id}` 查看状态，`DELETE /{id}` 请求取消。完成后仅返回 `result_ids`，通过原个人检测接口读取记录。重复预留同一 UUID 和参数返回原任务；文件已接收后不能再次上传。网络响应丢失应查询原任务，手动重试失败任务才创建新的 UUID。

任务限全局 8 项、每账户 4 项、原始上传文件预留总量 200 MiB，最多同时接收 2 个文件。上传按实际字节校验大小；未开始或中断上传空闲 180 秒过期。私有文件位于 `UPLOAD_DIR/.task-staging`，目录权限 0700、原始文件 0600；派生图片沿用原像素、视频帧数与尺寸限制，终态清理暂存。终态元数据最多保留 256 条、1 小时。

API 必须保持一个进程（Uvicorn `--workers 1`）：两个有界处理线程共用同一套 ONNX 会话和一个 FIFO 推理通道，视频逐帧让出通道，旧图片、视频和相机接口也进入同一通道。相机预览仍不自动保存；保存当前帧可作为普通图片任务提交。没有模型时，图片可指定作物保存为 `awaiting_model`；任务 `completed` 表示保存完成，不能解读为模型已完成检测。

任务仅在服务内存中保留，服务重启后原任务返回 404，需要重新提交；不提供刷新恢复或关闭程序后的恢复保证。任务按账户与 JWT 会话隔离。退出会话、会话失效或功能关闭时停止未完成任务；运行中的 ONNX 调用不强杀，结束后再次检查取消、会话与地块归属，再决定是否保存。取消先于提交则不保存任何记录，视频也不保留部分结果；提交先完成则保留已完成记录。

## 邮箱验证与密码找回

`GET /api/auth/config` 的 `password_reset_enabled` 表示 SMTP 主机、端口、TLS 模式、发件人和认证信息已配置完整；它独立于注册开关。`POST /api/auth/password-reset-code` 接收邮箱并统一提示，不透露邮箱是否存在、是否验证或账号是否停用；只有已证明归属的可用账户才会收到重置码。`POST /api/auth/password-reset` 接收 `email`、六位 `code` 和 10–128 字符 `new_password`，成功后要求重新登录，并撤销该账户所有旧会话及未完成检测任务。

历史 `user_emails` 记录只表示关联，不直接作为已验证证明。登录后可用 `GET /api/auth/email` 查看自己的邮箱与 `verified` 状态，通过 `POST /api/auth/email/verification-code` 获取绑定码，再调用 `POST /api/auth/email/verify` 提交 `email`、`code`、`current_password`。验证成功可绑定或换绑邮箱，保留当前登录；不允许占用其他账户的邮箱。旧邮箱证明及其待用重置码在换绑时失效。

验证注册或本人绑定成功时，以 `app_meta` 的 `verified_email:<SHA256(email)>` 保存用户 ID；不新增表或迁移。注册、重置、绑定验证码具有独立用途，数据库仅保存 HMAC 摘要，不能跨用途使用。验证码有效 10 分钟，60 秒内不能重发，最多尝试 5 次，并有每 IP/账户限额。找回与绑定邮件由一个有界后台发送线程处理，SMTP 延迟和异常不成为匿名账户查询依据；密码与验证码参数校验响应不回显输入。

管理员修改或解绑邮箱会清除该账户旧邮箱与目标邮箱的既有验证证明，并使相关待用重置码失效；目标被其他账户占用时先拒绝，保留对方证明。管理员来回修改邮箱不会自动恢复验证状态。重置验证码的 HMAC 还绑定签发时的账户 ID，后续邮箱转移不能让新账户使用旧账户的重置码。
