# 禾观 AgriScan · 农业智能检测平台

面向桌面浏览器的农业检测系统，采用 React + TypeScript + FastAPI + MySQL + Redis。界面围绕农田、作物健康与检测任务设计，并配有原创农业 IP 形象「小禾」。

当前版本提供业务数据管理、农业知识问答与真实叶片病害分类。仓库包含已训练的 PlantVillage 38 类 PyTorch 权重和 ONNX 推理模型；按下方说明启用后，上传图片使用真实模型推理。模型为单叶图像分类，不输出病斑框；未配置模型时只保存待接入任务，不生成虚构结果。

[查看桌面界面预览](design/dashboard-desktop.png) · [查看窄屏预览](design/dashboard-mobile.png) · [小禾 IP 原图](frontend/public/images/xiaohe.png) · [图像生成提示词与记录](design/mascot-prompt.txt)

## 从 GitHub 获取项目与权重

先安装 Git 与 Git LFS，再克隆仓库。权重以 Git LFS 保存；只取得指针文件时不能运行推理。

```powershell
git lfs install
git clone https://github.com/yuxiaopao/AgriScan.git
cd AgriScan
git lfs pull
git lfs fsck
```

仓库包含已发布的 `best.pt`、`model.onnx`、类别清单、评估报告和预训练权重，详见 [模型文件说明](models/README.md)。原始训练数据集、逐轮中间检查点、本地数据库、上传图片和真实 `.env` 配置不随仓库发布。

Windows 首次运行真实分类模型（在项目根目录执行）：

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-inference.txt
if (!(Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

在 `backend/.env` 中把 `MODEL_MANIFEST=` 设置为以下相对路径，然后启动：

```dotenv
MODEL_MANIFEST=../models/releases/plantvillage-yolo26m-906cf72f6bf0/manifest.json
```

```powershell
.\scripts\start-dev.ps1 -Install
```

打开 [http://localhost:5173](http://localhost:5173)，使用演示账号 `admin / admin12345` 登录；`/api/health` 中 `model: ready` 表示模型已加载。Python 需要 3.12 或更高版本，Node.js 需要 22.12 或更高版本。已有运行中的开发服务时，先执行 `scripts/stop-dev.ps1` 再重启以读取新配置。Docker 的默认配置仍需另外安装推理依赖并挂载模型，详见训练说明。

## 一键启动完整技术栈

要求 Docker Desktop 已启动并切换到 Linux 容器，且当前账户可以访问 Docker 引擎。

在项目根目录执行：

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

打开：

- 系统界面：[http://localhost:8080](http://localhost:8080)
- 后端 API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)
- 服务健康状态：[http://localhost:8000/api/health](http://localhost:8000/api/health)

首次构建会下载镜像并安装依赖。MySQL 初始化后，API 自动创建数据库表；演示模式会初始化示例数据。初始化过程需要等待一段时间，可通过以下命令查看：

```powershell
docker compose logs -f api
```

`.env.example` 默认开启 `DEMO_MODE=true`，适合本地体验。演示管理员为 `admin`，密码为 `admin12345`。示例密码和 JWT 密钥不可用于公开部署。

停止并保留数据：

```powershell
docker compose down
```

MySQL 数据、Redis 持久化数据和上传文件分别保存在三个 Docker 命名卷中。不要在需要保留数据时使用 `docker compose down -v`。首次初始化后更改 `.env` 中的 MySQL 密码不会自动更改数据库内已有账户密码。

默认仅向本机开放前端 `8080` 和后端 `8000` 端口，MySQL、Redis 仅在 Compose 内部网络访问。调整端口时请同时更新 `.env` 中的 `CORS_ORIGINS`。

## 不启动 Docker 的本地演示

要求 Node.js 22.12 或更高版本、Python 3.12 或更高版本。未配置数据库连接时，此方式默认使用 **SQLite 演示数据库**，不启用 Redis。连接 Docker 数据库见下文；完整容器部署请使用上面的 Compose 启动方式。

Windows 可直接在项目根目录运行开发脚本：

```powershell
.\scripts\start-dev.ps1 -Install
```

脚本会创建 `backend/.venv`、安装依赖、以隐藏进程启动两端并检查服务健康。后续启动可省略 `-Install`；指定 Python 可使用 `-Python "C:\完整路径\python.exe"`。日志在 `.logs/`，进程记录在 `.runtime/`。脚本使用本地演示配置；前端支持热更新，后端文件变更后请停止再启动。

```powershell
.\scripts\stop-dev.ps1
```

也可以手动使用两个终端，以便查看实时日志并使用后端热重载。

终端一，启动后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEMO_MODE = "true"
$env:DATABASE_URL = "sqlite:///./data/agriscan.db"
$env:REDIS_URL = ""
$env:UPLOAD_DIR = "./uploads"
$env:JWT_SECRET = "local-demo-change-this-secret-before-production-2026"
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "admin12345"
$env:CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

终端二，启动前端：

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

打开 [http://localhost:5173](http://localhost:5173)。前端开发服务器将 `/api`（包含 `/api/uploads` 图片接口）转发到本机 `8000` 端口。Windows PowerShell 如果阻止 `npm.ps1` 执行，可将命令中的 `npm` 替换为 `npm.cmd`。

SQLite 文件保存在 `backend/data/`，上传文件保存在 `backend/uploads/`，均已排除版本控制。两端分别按 `Ctrl+C` 即可停止。

## 本地开发连接 Docker 中的 MySQL 与 Redis

前后端在 Windows 本地运行时，可以只把 MySQL 和 Redis 放在 Docker Desktop 中。先准备项目根目录 `.env`，设置其中的数据库密码，然后执行：

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --wait mysql redis
```

`docker-compose.local.yml` 只向本机开放 MySQL `3306` 和 Redis `6379`。在 `backend/.env` 中配置以下连接，将数据库密码替换为根目录 `.env` 中的 `MYSQL_PASSWORD`；如果密码含有 URL 特殊字符，需要进行 URL 编码。

```dotenv
DATABASE_URL=mysql+pymysql://agriscan:<MYSQL_PASSWORD>@127.0.0.1:3306/agriscan?charset=utf8mb4
REDIS_URL=redis://127.0.0.1:6379/0
```

开发启动脚本会读取这些连接配置；未配置时仍默认使用 SQLite、关闭 Redis。修改后重新启动开发服务。新 MySQL 库由应用自动建表，并在演示模式初始化示例数据；不会自动导入旧 SQLite 数据，原数据库文件保留。

MySQL 和 Redis 数据分别持久化在 `agriscan_mysql_data`、`agriscan_redis_data` Docker 数据卷中，可在 Docker Desktop 的 Volumes 页面查看。停止数据库但保留数据：

```powershell
docker compose -f docker-compose.yml -f docker-compose.local.yml stop mysql redis
```

## 项目结构与请求链路

```text
AgriScan/
├─ frontend/             React + TypeScript + Vite 桌面管理界面
├─ backend/
│  ├─ app/               FastAPI API、数据模型及业务服务
│  ├─ requirements.txt   Python 依赖
│  └─ Dockerfile
├─ docker-compose.yml    MySQL + Redis + API + Nginx
└─ .env.example          本地环境变量模板
```

```text
浏览器
  └─ Nginx :8080 / Vite :5173
       ├─ React 页面与静态资源
       ├─ /api/* ────── FastAPI :8000 ── MySQL
       │                         └──── Redis
       └─ /api/uploads/* ── 带访问校验的上传图片接口
```

React 负责展示与交互；FastAPI 负责校验、认证和业务接口；MySQL 保存业务数据；Redis 实际用于看板 30 秒缓存，写入后清理缓存；Nginx 在容器环境统一转发 API 与上传图片请求。目前尚无推理队列或独立 worker。API 文档以运行后的 `/docs` 为准。

## 页面与主要流程

| 页面 | 浏览器路由 | 功能 |
| --- | --- | --- |
| 欢迎页 | `#welcome` 或无路由首页 | 小禾 IP 展示、产品介绍及账户入口 |
| 登录 / 注册 | `#login` / `#register` | 独立账户页面、可选邮箱验证码注册 |
| 总览工作台 | `#dashboard` | 作物与地块概览、趋势、近期任务、农业 IP 引导 |
| 作物检测 | `#detect` | 自动识别作物与病害、切换检测室、关联地块与小禾解读；无模型时采集样本 |
| 检测记录 | `#records` | 记录查询、筛选、详情与 CSV 导出 |
| 地块管理 | `#plots` | 地块新增、修改和删除、实景封面上传与移除、地图选点 |
| 病害知识库 | `#knowledge` | 浏览与检索作物病害知识、调用配置的大模型问答 |
| 模型管理 | `#models` | 上传训练权重、查看文件信息与 SHA256、删除登记 |
| 系统设置 | `#settings` | 服务状态、界面偏好、管理员查看邮件及大模型配置 |

首次访问进入欢迎页，通过独立登录页进入工作空间。自助注册账户为普通成员，可浏览共享业务数据、上传样本和使用小禾问答；地块修改、删除样本和管理权重需要管理员身份。演示模式允许匿名浏览示例数据。没有适配并启用模型时，图片上传后的任务状态为 `awaiting_model`，不生成虚构置信度或检测框。

编辑地块时，未保存的文字、坐标和待上传封面会自动缓存在当前浏览器的 IndexedDB 中，按账号和地块区分。关闭弹窗或刷新页面后重新编辑即可恢复；保存成功或点击“放弃草稿”会清除对应草稿。此缓存不在设备间同步，清理浏览器站点数据会移除草稿。地块卡片封面支持手动左右切换“封面 / 地图”两页，不自动播放、不首尾循环；地图页显示已保存的坐标标记，未定位的地块显示空状态。

点击“删除已有封面”只标记待删除，可通过“撤销删除”恢复，保存地块后才实际移除；删除标记也随草稿保留。选择新封面会取消待删除标记。封面替换或删除后，Windows 文件占用可能使旧文件暂留磁盘，但不会影响已保存结果，失去数据库引用的旧图片地址不可再访问。

## 注册、邮件验证与大模型配置

本地开发使用 `backend/.env`，Docker Compose 使用项目根目录 `.env`。对应 `.env.example` 已提供完整模板；本地首次配置可执行 `Copy-Item backend/.env.example backend/.env`，已有配置时直接编辑，避免覆盖。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `REGISTRATION_ENABLED` | `true` | 是否允许创建普通成员账户 |
| `EMAIL_VERIFICATION_ENABLED` | `false` | 注册是否必须通过邮箱验证码 |
| `SMTP_HOST` / `SMTP_PORT` | 空 / `587` | 邮件服务器及端口 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | 空 | 发信账号与授权码 |
| `SMTP_FROM` | 空 | 发信地址，需要与服务商允许的地址一致 |
| `SMTP_SECURITY` | `starttls` | `starttls` 一般配合 587，`ssl` 一般配合 465 |
| `LLM_ENABLED` | `false` | 是否启用知识库“小禾问答” |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | 兼容 Chat Completions 的 API 基础地址，填写到 `/v1` 等服务商要求的前缀，不包含 `/chat/completions`；远程地址须为 HTTPS，本机 `localhost` / 回环 IP 支持 HTTP |
| `LLM_API_KEY` / `LLM_MODEL` | 空 | 服务商 API 密钥与实际可用的模型名称 |
| `LLM_TIMEOUT` | `30` | API 超时秒数，允许 1–120 |
| `MODEL_MAX_UPLOAD_MB` | `200` | 单个权重最大体积，允许 1–2048 MB |

开启邮件验证前填写 SMTP 配置。验证码为六位数字，有效期 10 分钟，重发间隔 60 秒，最多尝试 5 次；服务端保存验证码摘要。关闭邮件验证时邮箱为选填。邮件和大模型接口都设有基础频率限制；当前限流为单进程内存实现，多进程或公开部署需增加网关或共享限流。

开启小禾问答需要同时设置 `LLM_ENABLED=true`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。问题由 FastAPI 转发到配置的服务；前端不会得到 API 密钥。普通问答响应只包含回答文本，不附带模型名称或服务地址；配置详情仅管理员设置接口可读取。问答属于通用农业知识回答，目前没有知识库检索增强（RAG）或图片诊断。管理员在系统设置页只能查看配置状态，实际更改仍以环境配置文件为准。

本地修改后执行 `scripts/stop-dev.ps1` 和 `scripts/start-dev.ps1`；Docker 修改后执行 `docker compose up -d --force-recreate api`，仅 `restart` 不会更新 Compose 环境变量。不要把密钥写到前端的 `VITE_*` 变量。若增大权重上限超过 200 MB，同时调整 `frontend/nginx.conf` 的 `client_max_body_size` 并重新构建前端容器。

### 小禾悬浮助手

工作空间各页面右下角均有透明背景的小禾入口，可拖拽移动，也可聚焦后使用方向键调整位置；点击展开小聊天窗，收起后仍可操作页面。支持 Enter 发送、Shift + Enter 换行、查看历史对话和新建对话。回复过程中收起窗口，完成时图标会显示新回复提示。

窗口展开时隐藏右下角图标，收起后恢复。拖动标题栏可移动窗口；聚焦标题栏后也可用方向键移动（Shift 加速）。位置在当前会话中保留，窗口始终限制在可见区域，调整浏览器尺寸后会自动适配。

上传检测成功后，小禾自动展开显示服务端已保存的检测结果，并向配置的 AI 服务发送经缩放、重新编码的叶片照片（最长边 1024 像素）及分类摘要，生成可见异常、虫害线索、处理步骤、复拍复检建议。此能力要求所配置的 Chat Completions 服务支持 `image_url` 图片输入。照片分析不能替代现场确认，也不把健康分类当作排除虫害的证据；无法辨认、没有虫害证据或尚无分类模型时应明确说明。模型服务不支持图片或调用失败时保留原检测，提供“重试图片解读”入口。

每个用户对同一检测的首次解读保存为独立历史对话，重复请求返回已有解读；不会覆盖原模型分类结果。对话关联保存在 `assistant_detection_discussions`，删除原检测不会删除已经保存的解读记录。普通用户看不到模型名称或接入配置。

对话与消息保存在数据库的 `assistant_conversations`、`assistant_messages` 表中，按当前账号隔离；管理员也不能通过对话接口读取其他用户的历史。刷新页面后打开小禾会恢复最近的对话。列表显示最近 100 段对话，每段最多 100 轮；继续聊天时服务端传递近期最多 10 轮、约 24,000 字符的历史上下文。发送失败保留已有记录和输入，方便重新发送；新对话使用独立上下文。普通问答内容中不附带模型配置。

### 作物检测室主题

模型就绪时，选择叶片照片并点击“识别并保存”，无需先选作物。模型从全部类别中同时判断作物与病害或健康状态，保存真实分数和候选；页面随后自动进入识别出的作物检测室，小禾自动展开补充照片分析、处理和复检建议。低置信度结果保留候选并提示人工复核。

检测页提供 17 种配色与对应手持作物的 8 帧小禾动画。模型就绪时，作物按钮仅用于浏览主题，不限制照片识别，也不修改已有结果或地块关联；刷新仍保留主题。当前权重覆盖 14 种作物，水稻、小麦和黄瓜标为“仅主题”。未配置模型时保留手动选择作物采集待检测样本的流程，不虚构自动识别结论。

地块为选填项，默认不关联。自动识别时可选择任意地块；识别出的作物与所选地块不符时，接口明确提示取消或更换关联，保留页面照片与备注供重试，不保存错误关联。检测进行中锁定照片、主题、地块和备注。

小禾入口保持透明且可拖拽。关闭“界面动效”或启用系统减少动态效果偏好后，角色停止动画；页面隐藏或角色离开视口时也会暂停。素材清单与生成记录见[作物主题与小禾素材](design/xiaohe-crops/README.md)。

## 后续接入训练权重

当前仓库已附带经过验证、供本项目显式启用的受信任发布权重与 ONNX 模型，启用方式见前文。以下流程适用于其他训练权重：

1. 确定训练框架、模型任务类型、类别表与输入尺寸，例如目标检测、分类或分割。
2. 管理员在模型管理页上传 `.pt`、`.pth`、`.onnx`、`.safetensors`、`.h5` 或 `.keras` 文件，填写名称与训练框架；权重保存在 `UPLOAD_DIR/models/`，数据库记录文件信息与 SHA256。上传后状态为“待验证与适配”，不自动反序列化或执行文件。权重默认被 Git 忽略。
3. 实现后端模型加载与推理适配，统一返回类别、置信度、框或掩膜、模型版本及耗时。
4. 将新权重接入真实推理流程，再启用与该任务对应的结果展示。
5. 使用真实验证集确认效果和阈值，再引入 GPU 镜像、任务队列、并发限制及监控。

模型管理页新上传的权重只登记保存，不会自动加载或执行；通过验证并完成适配后才能启用。系统不使用模拟推理冒充真实识别。

## 部署边界

这是可继续开发的本地系统起点。首次生产部署应使用独立的空数据库，关闭演示模式（`DEMO_MODE=false`），设置独立管理员密码及 JWT 密钥，并使用 MySQL 和 Redis。非演示模式要求管理员密码至少 12 个字符、JWT 密钥至少 32 个字符。

环境变量中的 `ADMIN_USERNAME`、`ADMIN_PASSWORD` 管理系统初始化管理员；修改后重启 API 会同步该账户，并让旧会话失效。存在账户冲突或无法唯一识别旧管理员时，服务会拒绝继续启动，需要先处理账户迁移。切换 `DEMO_MODE` 不会删除旧的示例记录，因此生产部署仍建议使用独立数据库。两个环境模板中的公开演示 JWT 密钥均不可用于生产模式。

还需要根据实际环境配置 HTTPS、域名、网络访问控制、数据库备份、审计日志、限流以及对象存储。Redis 默认仅在内部网络开放；需要跨主机访问时应配置认证与 TLS。生产数据库应引入版本化迁移；当前自动建表流程不能替代数据库迁移。

`/api/health` 返回数据库、Redis、运行模式和模型状态。Redis 不可用时系统退回数据库查询，并将状态标记为 `degraded`。当前为单组织共享工作空间，提供管理员与普通成员两类权限，注册成员可读取组织内全部业务数据；尚未实现多租户隔离或用户独立数据空间。不面向公开注册的组织应设置 `REGISTRATION_ENABLED=false`。

上传文件和业务数据请使用测试材料进行演示。现有页面是浏览器中的桌面风格应用，尚未封装为 Electron / Tauri 原生桌面安装包。

## 已完成的集成验证

2026-10-28，本次地块封面与界面整合后的后端全套自动化测试共 74 项通过。

本次账户与配置扩展：后端 24 项测试通过（SQLite 隔离数据库），覆盖注册开关、成员权限、验证码过期/次数/重发限制、权重上传/删除/格式与大小限制、大模型配置转发及密钥不回传。SMTP 与大模型服务使用测试替身，尚未连接真实服务商；新增前端通过 TypeScript 与 Vite 构建，并在浏览器检查欢迎、登录、注册、模型上传表单、配置面板及问答入口。

2026-10-20，在独立 Docker 项目中实际运行了 MySQL 8.4.11、Redis 7、FastAPI、Nginx，四个服务健康检查均通过。验证覆盖：

- 登录鉴权、地块增删改、图片上传与读取、查询筛选、看板缓存更新、注销令牌失效。
- 上传记录保存为 `awaiting_model`，结果和置信度为空；删除地块保留历史记录，删除样本同步移除图片。
- API 容器重建后，MySQL 数据和上传图片仍保留。
- 生产模式阻止匿名读取及图片访问；轮换管理员密码后，旧密码与旧令牌均失效。
- Nginx 可提供 React 页面、JS/CSS 和小禾图片，并正确转发登录、上传与带认证的图片请求。
- 后端 15 项自动化测试通过；前端 TypeScript 校验与 Vite 生产构建通过，图表资源已拆分。
- 浏览器实际验证登录、新建地块、选择并上传图片、记录筛选、异常指标跳转、CSV 下载及导出内容；联调样本与地块已清理，保留原始演示数据。
- 检查 1440 像素桌面与 390 像素窄屏布局，修复表格无障碍文本引起的横向溢出；浏览器控制台无错误或警告。
- Windows 开发启动/停止脚本已实际执行成功，修复 PowerShell 7 自动解析日期导致的进程时间戳精度问题。

验证时 Docker 构建环境访问 PyPI 出现 TLS 连接失败，因此 API 验证镜像使用从官方 PyPI 下载到本机的 Linux wheel 离线安装依赖；前端验证镜像使用本机已通过 TypeScript/Vite 构建的 `dist`。源码中的标准 Dockerfile 保持在线安装依赖的流程，**标准在线构建尚未在该网络环境下跑通**；需要可用的 Docker 网络或正确配置的代理。上述验证确认的是完整容器运行链路；临时测试容器和专用数据卷已清理，本地开发预览不受影响。

## 叶片病害分类训练

[PlantVillage 分类训练、断点恢复与模型接入说明](training/README.md)。训练进度和最终模型状态以 training/status.json 为准。


### 检测候选与浮动助手

检测完成后会保留实际模型前 5 项分类候选及原始概率（全类别排序，不按所选作物重新归一化），同时保存当次模型名称、任务和 ONNX 摘要。候选与模型快照位于 `detection_predictions` 新表，应用启动自动建表，兼容现有 SQLite/MySQL 数据；历史记录未存候选时不伪造补全。删除检测会一并删除其预测快照。

当前发布权重是 38 类单标签分类模型，候选列表不表示一片叶子同时患多种病。多病共存的判断需要多标签或病斑检测训练与验证，不能通过修改置信度来模拟。页面显示两位小数，极小非零分数显示 `<0.01%`，接近 1 的分数显示 `>99.99%`，浮点输出恰为 1 时显示 `≈100%`；原始值不截断或人为降低，置信度也不等于田间准确率。

小禾标题栏支持移动、缩小、最大化和还原，右下角手柄支持自由调整尺寸。标题栏与手柄均支持方向键（Shift 加速），尺寸限制在可见窗口内；收起时才显示右下角入口。最新检测与候选由服务端传给图片解读，自动展开窗口并保存对话。
