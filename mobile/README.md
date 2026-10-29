# 禾观手机 APP

独立的 React 手机界面，通过 Capacitor 运行在 Android；桌面用户端位于 `frontend/`，管理端有独立入口。APP 与桌面共享 FastAPI 服务、识别模型、地块和检测数据，小禾对话按账户隔离。

## 开发预览

需要 Node.js 22.12+。后端启动在 `http://127.0.0.1:18000` 后：

```powershell
cd mobile
npm.cmd ci
npm.cmd run dev
```

打开 `http://127.0.0.1:5174`。开发代理目标可通过环境变量 `AGRISCAN_API_PROXY` 修改。不要把其他项目占用的端口进程直接终止。

## 检测与交互

- 欢迎引导、登录、注册及邮件验证码（由管理员配置启用）。
- 图片上传后自动识别作物，展示病害、对应任务的置信度和候选结果；支持关联地块、备注和小禾分析。
- 视频使用真实模型对采样帧分别识别，展示时间轴；每帧作为一条共享观察记录保存。
- 实时相机按顺序抽帧识别，可暂停、继续、停止，并选择保存某次观察；退出页面或进入后台释放相机。
- 检测记录查询、详情、地块档案、知识搜索、小禾私人会话与历史、服务地址和界面偏好。

新目标检测接口提供真实目标框；旧分类模型保留兼容。目标框不是病斑精确轮廓，视频与相机按间隔抽帧，不进行连续跟踪或病程推断。识别需后端真实模型就绪；AI 分析需配置可用的大模型服务，服务失败时界面显示错误与重试。

## Android 与 APK

工程在 `android/`，应用 ID 为 `cn.agriscan.mobile`。构建需要 **JDK 21、Android SDK 36**，并设置本机 `JAVA_HOME` 和 `ANDROID_HOME`（或 `android/local.properties` 的 `sdk.dir`）。

若项目中存在 `.runtime/android-toolchain/`，脚本会自动使用其中的隔离 JDK、SDK、Gradle 缓存与 Android 用户目录，结束时恢复当前进程环境；不会修改系统 Java 设置。构建默认服务地址为 `https://agriscan.ming-ai.top/agriscan`，可通过 `VITE_API_BASE_URL` 或 `-ApiBaseUrl` 覆盖。

当前测试版为 **1.0.1 / versionCode 2**。使用新官方默认地址构建时，已保存的旧官方地址 `https://flowly-ai.top/agriscan`（含末尾斜线的同义写法）会在升级后迁移到新地址，并要求重新登录；自定义局域网或其他域名保持不变。服务地址对应的令牌相互隔离，不会把旧域名令牌转发至新域名。沿用原测试包签名的 APK 可作为升级包安装，仍需真机验证。

```powershell
# 仓库根目录：构建可安装的调试 APK
.\scripts\build-android.ps1

# 仅局域网调试：填写手机可以访问的电脑 IP，并显式允许 HTTP
.\scripts\build-android.ps1 -AllowLocalHttp -ApiBaseUrl http://192.168.1.20:18000

# 发布：HTTPS 服务，输出待签名 APK；签名密钥由项目所有者保管
.\scripts\build-android.ps1 -Release
```

调试产物在 `android/app/build/outputs/apk/debug/app-debug.apk`。发布版本需使用自己的 Android keystore 签名后分发。请勿提交密钥、密码或本机 `local.properties`。

手机安装后默认使用构建时写入的服务地址，也可在服务设置中更改。手机的 `localhost` 指向手机本身，不指向开发电脑。正式环境使用 HTTPS；后端 `CORS_ORIGINS` 需包含 `https://localhost`（Capacitor 默认 Android 来源）。相机首次使用需要系统授权；实际硬件相机和不同 Android 厂商的权限行为仍需真机验收。

小禾衍生素材及生成提示词见 `../design/app-assets/prompts.json`。
