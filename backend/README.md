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
| POST | `/api/detections` | multipart: `file, crop, plot_id?, note?` |
| GET / DELETE | `/api/detections/{id}` | 查询 / 删除检测 |
| GET | `/api/uploads/{filename}` | 查询已入库图片 |
| GET / POST | `/api/plots` | 地块列表 / 创建 |
| PATCH / DELETE | `/api/plots/{id}` | 修改 / 删除 |
| POST | `/api/plots/{id}/cover` | 管理员上传封面；multipart: `file` |
| GET | `/api/models` | 模型接入状态 |
| GET | `/api/knowledge` | 知识库 |

模型置信度字段范围为 0–1；地块 `health_score` 为已完成检测中健康结果的百分比（0–100），无已完成检测则为 null。`stats.pending` 包含等待模型、排队和处理中；失败记录只计入总数。

地块创建、修改支持可选的 `latitude`、`longitude`（WGS84），必须成对提交，同时为 null 时清除标记。地块列表返回 `cover_url` 和坐标；未设置时为 null。封面沿用图片格式、大小及像素校验，最长边缩至 1600 像素后保存为 JPEG，替换或删除地块时清理旧封面。封面上传独立于地块信息保存，上传失败可重试而不重复创建地块。

封面与坐标保存在新增的 `plot_details` 关联表，原有 `plots` 表不变。应用启动时 `create_all` 会创建此新表；现有数据库上线前需确认允许新增该表。前端地图采用 Leaflet 和 OpenStreetMap，底图依赖联网；底图不可用时仍可填写经纬度。

## 训练权重接入

`app/inference.py` 定义 `InferenceProvider` 接口和 `InferenceResult`。目前只注册 `AwaitingWeightsProvider`：图片保存后标为 `awaiting_model`，`result` 和 `confidence` 均为 null。系统**没有运行任何病害识别模型**。当前 Redis 用于看板缓存，尚未运行推理队列或 worker。

权重准备好后：

1. 实现与实际训练模型匹配的 provider，显式加载受信任权重和标签映射，固定预处理、阈值、模型版本。
2. 加入模型注册表、版本切换与启动加载检查，更新 `/api/models` 返回真实加载状态。
3. 将耗时推理移到独立 worker，以 Redis 队列传递检测 ID；保存任务状态与失败原因，提供幂等重试和重新分析接口。
4. 用独立验证集验证输出格式、分类 / 定位准确率和异常输入；再启用实际诊断。

## 部署与数据

`.env.example` 列出变量。`DEMO_MODE=false` 会拒绝默认密码、短 JWT 密钥、SQLite 和空 Redis URL。MySQL 和 Redis 的完整环境由仓库根目录 Compose 提供。

应用首次启动通过 SQLAlchemy 建表并建立由环境变量管理的管理员。每次启动都会将此账号的用户名和密码同步到 `ADMIN_USERNAME` / `ADMIN_PASSWORD`；修改这些变量并重启即可轮换凭证，旧密码和旧 JWT 随即失效。管理员身份 ID 保留，改用户名不会残留另一个演示管理员。请在各实例使用同一套凭证配置，避免启动时相互覆盖。生产模式拒绝两个内置示例 JWT 密钥；发现其他仍使用演示密码的旧账号会拒绝启动，需先重置或移除。

后续表结构变更应使用 Alembic 迁移，当前 `create_all` 不负责升级旧表。首次生产部署应使用独立空数据库，不要复用演示数据库；切换 `DEMO_MODE` 不会删除已有数据。`uploads/` 和数据库必须一起备份。

Redis 故障会令健康状态显示 `degraded`，业务仍可直接读写数据库。缓存失效失败时旧数据最多保留 30 秒。当前登录频率限制为单进程内的每来源地址 / 用户组合 5 分钟最多 10 次失败；多实例生产部署需在网关增加统一限流。当前为单组织管理员系统，不包含多租户隔离、用户注册和细粒度角色管理。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
