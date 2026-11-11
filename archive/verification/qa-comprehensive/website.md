# 官网真实浏览器 QA · 2026-10-28

**最终状态：部署阻塞。** 用户确认 `flowly-ai.top` 尚未完成ICP备案；国内直连 HTTP 返回腾讯 DNSPod 备案拦截页，HTTPS 连接失败。必须完成备案与腾讯接入后复验，不能称整站公网全通过。

| 检查范围 | 总数 | 通过 | 阻塞 | 未取得结果 |
| --- | ---: | ---: | ---: | ---: |
| 本地官网真实点击 | 34 | 34 | 0 | 0 |
| 真实公网域名 IAB 路径 | 28 | 27 | 0 | 1 |
| 国内公开部署门槛 | 1 | 0 | 1 | 0 |

本地、SSH源站验收入口及真实公网域名都检查了 320、390、768、1280、1920 五档宽度：无横向溢出，3张功能卡片的插画与标题/正文交叠面积均为0，7张图片全部加载。真实域名的4条导航、6条FAQ、跳过主内容与键盘菜单均已实际操作。17个链接目标逐一核对，全部保留 `/agriscan/` 前缀；工作台及管理端功能由父任务负责。

本地实际点击全部17个链接，工作台/管理入口仅检查落地，没有登录或提交业务操作。6条FAQ均点击展开、Enter收起。下载元数据重试在本地与真实域名均返回200。本地捕获44条资源事件，无HTTP错误或加载失败，控制台error/warn为0；真实域名重载捕获10条资源响应，均成功，控制台error/warn为0。

**已修复并部署一处键盘问题：** `website/app.js` 中Esc关闭菜单后原先焦点落到BODY；现恢复至菜单按钮，并同步“打开导航/关闭导航”名称。本地与真实公网域名均复验 `focusIsToggle=true`、`aria-expanded=false`，焦点轮廓可见。脚本SHA-256：`6900909abc3853633497a50dc47466a29c4873a774f7df044456cc2f83f9f6e9`。

**APK证据分别记录：** 本地经浏览器下载的文件为18,744,536字节，SHA-256=`7b195441f02683ef861aa8b35ed21ef4ebe6593e9de2b914b3c0f82cd24a2135`，精确匹配元数据。公网真实URL正常TLS HEAD返回200、`Content-Length: 18744536`、`Content-Type: application/vnd.android.package-archive`；未设置Content-Disposition，页面download属性为`agriscan-test.apk`。源站19:54:33+0800记录IAB公网来源74.2.4.80的APK GET为HTTP/2 200、body_bytes_sent=18,744,536。浏览器下载完成事件工具未返回，因此没有宣称公网浏览器已保存文件及核验其SHA。没有安装或运行APK，不再重复等待该事件。

**公网路径限制：** CUA IAB直接打开 `https://flowly-ai.top/agriscan/`，未设DNS/resolve/代理、未绕过证书；初次有ConnectionClosed，重试后成功。唯一探测URL `?qa_probe=website_20261028_asset_check` 在源站19:58:41+0800记录HTTP/2 200、来源74.2.4.80，证明不是5180代理的请求。出口地区未验证，不能代表中国本机或全球。独立web工具仍无法读取同URL，本机curl仍握手失败/HTTP302；用户确认未备案使国内阻塞原因明确。

未测试原生APP或5174，没有修改网络与部署。截图见 `design/qa-20261028/website-public-*.png`，尤其 `website-public-download-ready.png`。完整逐项记录见同目录 `website.json`。
