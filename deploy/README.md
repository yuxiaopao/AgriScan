# 禾观服务器部署

部署目标为现有 SSH 别名 `tencent-server`，服务器 `162.14.71.77`，域名 `agriscan.ming-ai.top`。

| 入口 | 地址 |
| --- | --- |
| 官网 | https://agriscan.ming-ai.top/agriscan/ |
| 桌面网页版 | https://agriscan.ming-ai.top/agriscan/workspace/#login |
| 独立管理端 | https://agriscan.ming-ai.top/agriscan/admin/ |
| APP 发行信息 | https://agriscan.ming-ai.top/agriscan/downloads/release.json |

现有 Flowly 根站点、`/app.apk` 和 `flowly-share.service` 保留。新域名使用独立的 `/etc/nginx/conf.d/zz-agriscan.conf`，复用现有 `/agriscan/` 路由与业务数据；根 `/` 跳转到 `/agriscan/`。

## 运行环境

OpenCloudOS 9.6，MySQL 8.0.45、Redis 7.2.15、系统 Nginx、独立 Python 3.11.6 venv。生产仅运行 CPU ONNX 推理，不安装 PyTorch。

- `/srv/agriscan/releases/`：按时间存储代码、网页和已验证模型。
- `/srv/agriscan/current`：当前版本软链接。
- `/srv/agriscan/venv`：独立运行依赖。
- `/srv/agriscan/shared/production.env`：生产配置与凭据，`root:agriscan`、0640；不在仓库或网页目录。
- `/srv/agriscan/shared/uploads`：用户图片与模型产物。
- `/srv/agriscan/shared/backups`：Nginx 变更前备份。
- `/var/www/sites/agriscan`：指向当前版本网页目录。

服务为 `mysqld`、`agriscan-redis`（只监听127.0.0.1:16380）、`agriscan-api`（只监听127.0.0.1:18000）。Nginx 通过 `/agriscan/api/` 代理 API。MySQL 只监听回环地址，应用使用独立 `agriscan` 数据库和账号。

新装 MySQL 的 root 账号已设置强密码，仅保存到 root 专用的 `/root/.my.cnf`（0600），没有打印或放入应用目录。shared 根目录和生产配置由 root 管理，应用仅对 uploads、logs 目录有写权限。

`setup-host.py` 初始化独立账户、运行目录和服务，并生成强凭据；已有生产配置会被保留。数据库采用生产模式，不迁移本机演示账号、示例检测或本机小禾服务密钥。大模型默认未启用，管理员可在「系统配置」填写可用服务。

## 构建与发布

桌面构建设置 `VITE_WEB_BASE=/agriscan/workspace/`、`VITE_API_PREFIX=/agriscan`、`VITE_ADMIN_URL=/agriscan/admin/`；管理端设置 `VITE_ADMIN_BASE=/agriscan/admin/`、相同 API 前缀及 `VITE_WORKSPACE_URL=/agriscan/workspace/#login`。静态素材通过构建期路径转换随应用前缀发布。

发布包只包含后台源代码、迁移、依赖清单、网页编译产物、官网和已验证的 `model.onnx` / `manifest.json`。不包含 `.env`、SSH 密钥、数据集、训练环境、node_modules、本机数据库或175MB原始权重。

`upload-release.py` 将归档通过 SSH 分块传输，最终必须核对完整 SHA256。`activate-release.py` 再核对归档和 ONNX 校验值，在独立目录解包，切换当前版本、启动 API，健康检查通过后才添加 Nginx include；运行 `nginx -t` 成功后 reload。共享路由片段是 `/etc/nginx/agriscan-locations.inc`，新域名的独立配置为 `/etc/nginx/conf.d/zz-agriscan.conf`。启用发布前必须先配置该虚拟主机及可信证书；可用 `AGRISCAN_DOMAIN`、`AGRISCAN_NGINX_CONFIG` 显式覆盖目标。旧 Flowly 虚拟主机不作为新发布脚本的默认编辑目标。

当前检测包来自用户 `best.pt`，38类，目标框为原图归一化 `xyxy`。已修正 Ultralytics 旧版双头权重的推理分支兼容问题，并完成5图 PyTorch/ONNX 一致性验证；没有独立检测 mAP，不使用旧分类模型成绩。细节见 `models/candidates/user-detect-fafc2bb3ce9e/README.md`。

Android 使用 `scripts/build-android.ps1`，默认生产 API 是 `https://agriscan.ming-ai.top/agriscan`。已实际构建调试签名的公开测试版 `cn.agriscan.mobile` v1.0.1 / code2，Android 7.0+、四种 ABI，18,744,600 字节；签名 v2、ZIP、清单和默认 HTTPS 配置均核验通过；1.0.1沿用原测试签名，可覆盖安装，升级后旧官方服务地址迁移至新域并重新登录。尚未进行真机交互验收。

官网只在真实 APK、签名校验、大小及 SHA256 核对后把 `downloads/release.json` 标为 ready；安装包用 `upload-artifact.py` 单独传输、核对并原子发布，密钥和工具链不进入静态目录。当前测试包 SHA256 为 `ab5ed73430cc0aea17b403377ede3f3d7e686cef2346b94aed1cc4d9e7d93f85`。测试版不等于正式签名发行；后续正式分发需项目所有者保管稳定的发布签名。

## 运维与验收

```bash
systemctl status agriscan-api agriscan-redis mysqld
journalctl -u agriscan-api -n 50 --no-pager
curl http://127.0.0.1:18000/api/health
nginx -t
```

`smoke-server.py` 通过受限的生产凭据登录，验证真实目标框、持久化、图片鉴权、空背景422、配置热更新及版本冲突；只清理本脚本创建的数据，配置按 CAS 恢复，不输出密码或令牌。首次服务器验收已通过，短时观察服务内存峰值约608.9MiB，不能当作压力测试结论。

2026-10-29 已从旧域名迁移到 `agriscan.ming-ai.top`。旧域的 2026-10-28 验收与备案拦截记录保留在历史报告中，不改写为新域的测试结果。新域已验证正常 DNS 公网访问、HTTPS 证书、域名根跳转、登录、检测与 APK 下载；不能用源站 `--resolve` 自检替代外部浏览器检查，也不关闭证书校验。详见[域名迁移验收](../docs/domain-migration-20261029.md)。

回滚时先确认目标为 `/srv/agriscan/releases/` 下已保留的版本，再原子替换 `current` 软链接、重启 `agriscan-api`。用户上传、生产配置和数据库在 shared/独立服务中，按版本切换不会删除。数据库与 `CONFIG_ENCRYPTION_KEY`、JWT配置、上传文件应分别保留安全备份。
