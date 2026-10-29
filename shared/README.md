# 共享检测任务核心

`detectionTasks.ts` 为网页和 APP 提供同一套上传队列、进度、状态恢复与取消逻辑，任务生命周期由各端的登录会话管理。

在项目根目录使用 Node.js 22.12 或更新版本运行：

```sh
npm --prefix frontend ci
node --test shared/tests/detectionTasks.test.mjs
node --test shared/tests/accountValidation.test.mjs
```

已有前端依赖时可跳过安装。测试使用前端现有的 TypeScript 开发依赖，在内存中转译实际核心源码；通过公开接口和可控的 HTTP / XHR 事件验证行为，不连接公网、SMTP、数据库或推理服务，也不生成构建产物。

覆盖上传与轮询不同步、按 UUID 恢复丢失的任务创建响应、已排队任务不重复上传、取消优先级、429 退避、终态与进度保持、并发限制及账号隔离。每个测试清理任务管理器，并核对请求、轮询定时器与上传传输均已释放。

`accountValidation.ts` 与 `apiErrors.ts` 统一网页、管理端和 APP 的用户名规则与中文校验提示。账号测试覆盖普通用户名、邮箱格式用户名、边界长度、非法邮箱与服务端校验错误的安全展示；不会回显请求输入或技术正则。
