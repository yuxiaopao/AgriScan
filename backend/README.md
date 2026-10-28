# 禾观 AgriScan API

Python 3.12 + FastAPI + SQLAlchemy。完整部署使用 MySQL 8 和 Redis；本地演示默认使用 SQLite，Redis 可以关闭。

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

交互式接口文档：`http://localhost:8000/docs`。本地演示账号 `admin / admin12345`。`DEMO_MODE=true` 时只读接口公开，所有写接口都需要 `Authorization: Bearer <token>`；正式模式所有业务读写和上传图片访问都需要登录。图片用于浏览器展示时，正式模式需用带凭证的 fetch 读取 Blob。

## 已实现

- JSON 登录、JWT 会话、获取当前用户、令牌注销与持久化吊销记录；密码 PBKDF2 哈希存储，密码轮换自动使旧 JWT 失效。
- 数据看板：数据库真实聚合，7 / 30 天趋势，Redis 30 秒缓存，写操作清理缓存。
- 检测记录：图片上传、筛选、详情、删除。图片必须可解码为 JPEG/PNG/WebP，限制 10 MB / 2500 万像素；解码后重新编码，移除元信息，随机文件名持久化。
- 地块管理：新增、修改、删除、实景封面和地图定位。删除地块保留历史检测并解除关联；存在关联检测的地块不可变更作物。
- 模型管理状态、作物支持列表、静态知识库。知识库为一般性巡检提示，不能代替农技人员的现场判断。
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

封面与坐标保存在新增的 `plot_details` 关联表，原有 `plots` 表不变。应用启动时 `create_all` 会创建此新表；现有数据库上线前需确认允许新增该表。前端地图采用 Leaflet 和 OpenStreetMap，底图依赖联网；底图不可用时仍可填写经纬度。

## 训练权重接入

`app/inference.py` 定义 `InferenceProvider` 接口和 `InferenceResult`，包含 `OnnxClassificationProvider` 与 `AwaitingWeightsProvider`。仓库附带经过验证的 PlantVillage 发布模型，覆盖 14 种作物、38 个类别，属于单叶图像的单标签分类，不输出病斑框，也不能据此判断多病共存。

在 `backend/` 中安装 `requirements-inference.txt`，并在 `backend/.env` 设置 `MODEL_MANIFEST=../models/releases/plantvillage-yolo26m-906cf72f6bf0/manifest.json` 后重启 API，即可启用该 ONNX 模型。启动时校验清单、类别、预处理、输入输出形状及模型 SHA256；`/api/health` 中 `model: ready` 表示模型已加载。详细说明见[模型文件说明](../models/README.md)及[训练与接入说明](../training/README.md)。

未配置 `MODEL_MANIFEST` 时使用 `AwaitingWeightsProvider`，手动指定作物采集图片后标为 `awaiting_model`，`result` 和 `confidence` 均为 null；自动识别请求返回明确错误。配置的模型无法通过加载校验时，服务启动失败，需要修正配置。模型管理页上传的权重仅登记保存，不自动反序列化、加载或执行。

当前推理在 API 进程中执行，Redis 仍用于看板缓存，尚未运行推理队列或独立 worker。其他权重需要按实际任务适配 provider、明确类别映射与预处理，并通过独立验证后显式启用；队列、模型版本切换等能力仍需后续实现。

## 部署与数据

`.env.example` 列出变量。`DEMO_MODE=false` 会拒绝默认密码、短 JWT 密钥、SQLite 和空 Redis URL。MySQL 和 Redis 的完整环境由仓库根目录 Compose 提供。

应用首次启动通过 SQLAlchemy 建表并建立由环境变量管理的管理员。每次启动都会将此账号的用户名和密码同步到 `ADMIN_USERNAME` / `ADMIN_PASSWORD`；修改这些变量并重启即可轮换凭证，旧密码和旧 JWT 随即失效。管理员身份 ID 保留，改用户名不会残留另一个演示管理员。请在各实例使用同一套凭证配置，避免启动时相互覆盖。生产模式拒绝两个内置示例 JWT 密钥；发现其他仍使用演示密码的旧账号会拒绝启动，需先重置或移除。

后续表结构变更应使用 Alembic 迁移，当前 `create_all` 不负责升级旧表。首次生产部署应使用独立空数据库，不要复用演示数据库；切换 `DEMO_MODE` 不会删除已有数据。`uploads/` 和数据库必须一起备份。

Redis 故障会令健康状态显示 `degraded`，业务仍可直接读写数据库。缓存失效失败时旧数据最多保留 30 秒。当前登录频率限制为单进程内的每来源地址 / 用户组合 5 分钟最多 10 次失败；多实例生产部署需在网关增加统一限流。

当前为单组织共享工作空间，提供管理员和普通成员两类角色。允许注册时，新账户为普通成员，可读取组织内共享业务数据、上传检测样本并使用小禾问答；地块修改、删除样本和权重管理需要管理员身份。可通过 `REGISTRATION_ENABLED=false` 关闭注册，注册流程还支持可配置的邮箱验证；尚未实现多租户隔离或更细粒度的权限管理。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

2026-10-28：本次整合后后端全套自动化测试 74 项通过。
