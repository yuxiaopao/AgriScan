# 禾观管理控制台

独立管理应用，默认端口 `5175`，与桌面用户端和手机 APP 分开运行。

```powershell
cd admin
npm.cmd ci --cache ../.runtime/npm-cache
npm.cmd run dev
npm.cmd run build
```

共享组件依赖用户端的包，首次运行前还需在 `frontend/` 执行 `npm.cmd ci`。API 默认代理到 `http://127.0.0.1:18000`，优先读取 `AGRISCAN_API_PROXY`，兼容 `AGRISCAN_API_TARGET`；两者均支持环境变量和 `.env`。根目录 `scripts/start-clients.ps1` 可一起启动三个客户端。

开发时“返回用户工作台”指向当前主机的 `5173`，生产默认指向 `/`。可用 `VITE_WORKSPACE_URL` 配置完整地址。生产构建默认 `base=/admin/`；单独域名部署设 `VITE_ADMIN_BASE=/`。部署时 `/api`、`/uploads` 需配置同源反向代理，静态品牌文件使用 `/brand`、`/images` 根路径。

管理员必须单独登录。构建配置固定 `VITE_APP_SURFACE=admin`，共享 API 客户端及共享组件使用 `sessionStorage` 的 `agriscan-admin-token`；用户端仍使用 `agriscan-token`。普通成员会被拒绝并清空管理端令牌。服务器 `/admin/*` 接口继续执行管理员权限检查。

主界面维护成员、地块、检测、知识、模型、日志与系统状态。基础组件、地块编辑器及样式在 `../frontend/src/` 共享；`publicDir` 复用静态品牌素材，不包含上传数据。

## 大模型配置与连接测试

管理员登录后进入“系统配置 → 小禾大模型服务”。可一键填入 DeepSeek 官方地址与 `deepseek-flash` 模型，也可填写其他兼容服务。密钥支持保留、替换和清除；保存后由后端加密写入 `workspace_configuration` 数据库表，管理接口只返回“已配置”状态，不返回原始密钥。

“测试连接”检查当前草稿的文字回复和测试图片理解，会产生少量服务商调用，但不会保存、启用配置或修改数据库版本。地址变更后需提供对应的新密钥，不能把原服务密钥带到另一个地址。测试中暂时禁用编辑和保存；修改地址、模型、超时或密钥后，旧测试结果会失效。确认测试结果后，开启接入并点击“保存所有配置”，新请求会使用已保存的配置。

测试通过只表示服务连通及支持所测图片输入，不代表农业诊断准确率；模型名称和可用能力仍以服务商实际响应为准。浏览器不保存密钥草稿到本地存储。

## Docker 与 Nginx

Dockerfile 使用仓库根目录作为构建上下文，同时安装共享组件所需依赖；镜像运行时只包含编译产物。专属忽略文件排除模型、数据集、运行数据与本机配置。

```powershell
# 仓库根目录；独立域名（base=/）
docker build -f admin/Dockerfile -t agriscan-admin --build-arg VITE_WORKSPACE_URL=https://agriscan.example.com .

# 与用户端同域，网关把 /admin/ 转发到此容器
docker build -f admin/Dockerfile -t agriscan-admin --build-arg VITE_ADMIN_BASE=/admin/ .
```

容器应加入现有 API 的 Docker 网络，API 服务名为 `api`、端口 `8000`；端口 `80` 交给 HTTPS 入口代理。Nginx 配置兼容 `/` 和 `/admin/` 的静态路径，并把接口转发给 `api:8000`。其他部署方式按实际 API 主机修改 `nginx.conf` 的上游地址。生产密钥仍只配置在后端。

同域部署时，网关将 `/admin/` 转发到本容器，用户端负责根路径品牌素材；独立域名时，管理容器自身提供素材。`VITE_WORKSPACE_URL` 只用于返回链接，域名、TLS、API 上游不会由客户端环境变量自动配置。
