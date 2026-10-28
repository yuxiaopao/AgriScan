# 2026-10-28 生产部署与公网访问证据

生产入口：<https://flowly-ai.top/agriscan/>；工作台 `/agriscan/workspace/`；管理端 `/agriscan/admin/`。本轮运行标识 `qa20261028_1935`，以下时间为北京时间，证书日期另标 UTC。

## 当前结论

**用户已明确确认该域名尚未完成备案。** 当前电脑保留域名 Host/SNI、直连真实公网 IP 的 HTTP 请求，被 302 导向腾讯备案拦截页；HTTPS 握手被关闭。这与域名未备案事实相互印证。

服务器本机通过正常 DNS、公网 IP 访问网站和 API 成功；独立 IAB 浏览器直接访问域名也成功，源站日志证明该浏览器出口为 `74.2.4.80`。这些成功路径不能用来承诺中国各网络或全球均可访问。

本轮没有修改域名、备案、系统网络、TLS、Nginx 或原有 Flowly 配置。主任务完成 QA 业务清理后，按最终授权只删除指定 QA 账户、文章与对话；真实业务记录保留。备案需由用户本人按实际主体流程完成。

## 四轮最小修复部署

当前 release：`/srv/agriscan/releases/release-20261028-190106`，`current` 链接保持该 release。

| 批次 | 同步内容 | 备份与结果 |
| --- | --- | --- |
| 19:55 首轮 | 7 个变更文件：后端 `admin.py`、工作台/管理端新 bundle 与 index、官网 `app.js` | 92 个文件哈希相同未上传；约 300 KB 包；先静态 assets、后两个 index；所有替换文件通过 TLS 内容哈希核对 |
| 20:04 第二轮 | 仅 5 个静态变更文件：工作台与管理端 bundle/index | 92 个文件未变；约 292 KB 包；先 assets 后 index；逐文件 TLS 哈希通过；API 未重启 |
| 20:09 欢迎页修复轮 | 仅工作台 3 个变更文件：欢迎页中性说明对应的 bundle、Dashboard chunk、index | 46 个文件未变；约 152 KB 包；先两个 JS 后 index；逐文件 TLS 哈希通过；管理端未变，API 未重启 |
| 20:18 窄屏修复轮 | 仅工作台 4 个文件：两个 JS、响应式 CSS、index | 约 180 KB 包；先 JS/CSS 后 index；逐文件 TLS 哈希通过；API 未重启；768/900/1024 浏览器复验由主任务完成 |

首轮备份：`/srv/agriscan/shared/backups/qa20261028_1935-repair-20261028T115505Z`。

第二轮备份：`/srv/agriscan/shared/backups/qa20261028_1935-ui2-20261028T120446Z`。

欢迎页修复轮备份：`/srv/agriscan/shared/backups/qa20261028_1935-ui3-20261028T120916Z`。

窄屏修复轮备份：`/srv/agriscan/shared/backups/qa20261028_1935-ui4-20261028T121811Z`。

最终部署文件：

| 文件 | SHA256 |
| --- | --- |
| 后端 `backend/app/admin.py` | `587e8170b43bab1a0cc4feb931d930636fc954ba626fa773a0a34d7e9d1de539` |
| 工作台 `assets/index-C8ROKbOw.js` | `4e53c013d946c3466086dce2c7b10c74be3a8fb96153e06d405f3e29aaca7ca9` |
| 工作台 `assets/Dashboard-D9OfT1QS.js` | `2481ed3edd85363331a66f0e0d7921dd8902d8d8061db58e0a746216ff8c0eda` |
| 工作台 `assets/index-8PSuoOsD.css` | `f3216653e4e348a2f41b0af271a0ad7299814e5c6e16fb3e6b76cd67e7c7443a` |
| 管理端 `assets/index-CsHJvBm3.js` | `6566003fddc8b84ad0b3ecf2104e09cd1b9bdf32791511b2a9513ee5468edb42` |
| 官网 `app.js` | `6900909abc3853633497a50dc47466a29c4873a774f7df044456cc2f83f9f6e9` |

工作台 base 为 `/agriscan/workspace/`，管理端 base 为 `/agriscan/admin/`，两端 API prefix 为 `/agriscan`；实际 index 引用与本地构建资源一致，无缺失文件。

后端首轮仅按授权重启一次，最终 PID `1144975`、`active/running`、`NRestarts=0`。后三轮前后 PID 相同。生产健康返回数据库与 Redis 已连接、模型 ready。窄屏修复轮结束时服务 cgroup 内存峰值约 663.5 MiB；这不是并发压力测试。

20:08 的只读补核确认配置前后均为 v5；本轮真实 QA 检测 `59c412046b7046ffb547e0b28f3bdb3d` 的 CSV 内容与筛选列表一致，保存框坐标在管理/用户 API 中相同，原图授权读取成功、匿名读取 401。此时未清理 QA 数据，脚本只注销自身会话。

主任务已完成最终公网窄屏复验：768 宽度 client/scroll 为 753/753，900 为 885/885，901 为 886/886，1024 为 1009/1009。面包屑恢复正常，768 导航可折叠；再次上传真实横图得到健康类别、98.68% 独立检测分数和 1 个真实框。

修复后的完整后端测试为 **192 passed, 1 skipped**，149.14 秒。跳过项为本机 Windows 缺少符号链接创建权限。混作物目标事后关联地块的漏洞已先复现失败，再修复并通过相关及完整回归。

## DNS、TLS 与服务器网络

| 检查 | 证据 |
| --- | --- |
| DNS A | 系统解析、`dig`、阿里 DoH、Google DoH 均得到 `162.14.71.77` |
| apex/www 的 AAAA、CNAME | 查询成功，均无对应记录；www A 同为 `162.14.71.77` |
| 证书 | CN `flowly-ai.top`；SAN `flowly-ai.top`、`www.flowly-ai.top` |
| 签发者 | Let's Encrypt YE2 |
| 证书有效期 | 2026-10-26 02:23:08 至 2027-01-24 02:23:07 UTC |
| TLS 校验 | 服务器正常 DNS 连接返回 `Verify return code: 0 (ok)`；未关闭证书校验 |
| Nginx | 匹配 apex/www 域名，包含 `/agriscan/` 配置；`nginx -t` 通过 |
| 监听 | IPv4 `0.0.0.0:80/443`、IPv6 `[::]:80/443` 均监听 |
| 主机防火墙 | firewalld 未运行；iptables INPUT 默认 ACCEPT；未更改任何规则 |
| 跨域与上传 | 源站 POST 检测预检 200，允许 `https://flowly-ai.top`、Authorization/Content-Type；Nginx 2050 MB、body timeout 180 秒、proxy read timeout 300 秒 |

未查询云账号安全组或备案账号内部记录。主机网络检查不代表所有上游链路均放行。

## 不同访问路径的实际结果

| 观察位置与路径 | HTTP | HTTPS | 解释边界 |
| --- | --- | --- | --- |
| 腾讯服务器本机、正常 DNS 到公网 `162.14.71.77` | 301 至 HTTPS | 官网及 API 均 200 | 属服务器自身公网访问，不能替代外部用户验证 |
| 服务器 loopback，域名 Host/SNI 与证书验证保留 | 301 | 官网/API 200 | 只作为源站控制组 |
| 独立 CUA IAB 浏览器直域名，未用 5180/手工 resolve | — | 主页面、资源及下载描述均 200；登录与真实图片检测成功 | 源站日志出口 `74.2.4.80`，地区未验证 |
| 当前 Windows 电脑、正常系统 DNS | 301 | schannel 握手失败，curl 35 | DNS 被 Sing-tun 映射为 `198.18.0.133`，不能当作普通直连 |
| 当前 Windows 电脑、保留域名且强制真实公网 IP | 302 至腾讯备案页 | schannel 握手失败，curl 35 | 数据包仍可能经过本机 TUN 路由；是该实际网络路径的拦截证据 |
| 外部网页抓取工具 | 无状态码 | 无状态码 | 工具报告不可访问，不能据此判断站点故障原因 |

302 的实际 Location：<https://dnspod.qcloud.com/static/webblock.html?d=flowly-ai.top>。该腾讯官方页面可读取，标题为“备案”，显示“网站暂时无法访问”及备案控制台入口。用户明确确认尚未备案；本轮未尝试改变或规避该流程。

服务器日志中本轮专属 UA 的 6 条记录与正常公网/loopback请求相符，HTTPS 均 200、HTTP 均 301；对应专属错误日志为空。IAB 的独立 `qa_probe=website_20261028_asset_check` 日志记录来源 `74.2.4.80`、主页面 200，并完成菜单 Esc 回焦和按钮名称修复复验。

## 原始证据

服务器日志目录 `/srv/agriscan/shared/logs/` 与本地 `.runtime/qa-comprehensive/` 对应保存：

- `qa20261028_1935-repair-deployment.json`：首轮备份、逐文件 old/new SHA、写入顺序、服务健康。
- `qa20261028_1935-ui2-deployment.json`：最终静态构建、逐文件 SHA、API PID 未变化。
- `qa20261028_1935-ui3-deployment.json`：最终工作台三文件、逐文件 SHA、API PID 未变化。
- `qa20261028_1935-ui4-deployment.json`：最终窄屏修复四文件、逐文件 SHA、API PID 未变化。
- `qa20261028_1935-public-network-server.json`：DNS、HTTP/HTTPS、证书、监听、防火墙、Nginx、CORS 与本轮日志。
- `public-network-client.json`：当前 Windows 正常 DNS 与真实公网 IP 控制组。
- `dnspod-blockpage-summary.json`、`dnspod-blockpage.html`：腾讯备案拦截页。
- `ui2-build-inspection.json`：最终两端 base、API prefix、实际 index 资源引用。
- `ui3-build-inspection.json`：最终工作台 base、API prefix、实际 index 资源引用。
- `ui4-build-inspection.json`：窄屏修复最终工作台 base、API prefix、CSS/JS 与 index 引用。
- `qa20261028_1935-backend-readonly-final.json`：本地最终只读 API、配置 v5、非空 CSV/图像权限补核；服务器名为 `qa20261028_1935-backend-readonly.json`。

后端完整测试与接口矩阵见 [qa-20261028-backend.md](qa-20261028-backend.md)。本轮报告不含密码、令牌或私钥。

## 最终 QA 清理与完整性

主任务已通过 API 精确删除 4 个已登记 QA 检测及其图片、1 个 QA 地块及封面，并注销测试会话。媒体验收只删除自身返回的 2 个采样检测，不删除既有业务记录。

随后按最终授权执行经过只读预览、精确白名单、外键与触发器保护的 ORM 清理：

| 对象 | 实际删除 |
| --- | --- |
| 三个专用 QA 用户 | 3 |
| 指定且已归档、标题带 QA 前缀的文章 | 1 |
| 仅归属 QA 用户的对话 | 1 |
| 检测对话关联、消息、用户邮箱 | 0 |

成功报告状态为 `passed_applied_and_verified`。清理前后：

- 原管理员完整行哈希相同；原有 4 篇知识完整内容哈希相同。
- ONNX 与 manifest 文件哈希相同；数据库配置与公共配置哈希相同，版本仍为 v5。
- 26 条审计记录的 ID 集合哈希相同；没有删除审计记录。
- 非 QA 检测共 2 条，清理前后均保留；没有将全库归零作为清理目标。
- 普通域名 HTTPS 健康检查前后均正常，MySQL/Redis connected、模型 ready。

清理未重启服务。最终证据为服务器 `/srv/agriscan/shared/logs/qa20261028_1935-final-cleanup-integrity.json`，本地 `.runtime/qa-comprehensive/qa20261028_1935-final-cleanup-integrity.json`。
