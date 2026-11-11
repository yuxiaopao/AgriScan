# PlantVillage 叶片病害分类训练

本流程使用用户提供的 `F:\QQ文件储存\yolo26m.pt`，把检测模型的完整 11 层骨干迁移到 38 类分类头。训练前逐一验证了 300 个骨干张量与原权重完全一致。任务是整张单叶图像分类，不产生病斑框。

## 数据与可重复性

- 原始项目：https://github.com/spMohanty/PlantVillage-Dataset/tree/master/raw/color
- 下载源：原作者在 README 推荐的 `mohanty/PlantVillage` 镜像，固定版本 `9e97599868962bd0079b8db4b7f1efa9185fa1e7`。
- `datasets/plantvillage/raw/color`：54,305 张图片、38 类；全部通过图片解码检查。
- 划分：训练 37,821 张、验证 5,485 张、封存测试 10,999 张。
- 用叶片分组与文件 SHA256 联合隔离三个集合，保留官方测试组，并将发现的跨集合重复组整体归入测试集；验证集仅从训练部分产生。
- `dataset-report.json` 保存计数、类别及泄漏审计；`manifest.jsonl` 保存逐图来源、分组、摘要和归属。
- `classification/train`、`val`、`test` 使用硬链接，不能把其中的文件原地编辑当作数据增强，否则会改变原图。
- 种子、训练参数、质量门槛集中于 `training/config.json`。实际环境保存在 `environment.json` 和 `requirements-lock.txt`。

## 查看训练进度

在项目根目录运行：

```powershell
Get-Content .\training\status.json
Get-Content .\runs\classify\plantvillage-yolo26m\results.csv -Tail 5
Get-Content .\.logs\training\bootstrap.err.log -Tail 20
nvidia-smi
```

配置最多 40 轮，验证指标连续 8 轮不改善时提前停止。每轮保存 `best.pt`、`last.pt` 和单独轮次检查点。`best.pt` 由验证集选择；测试集不参与选择、调参或提前停止。

运行中的主流程：

1. 校验数据清单、原权重摘要及 CUDA 可用性。
2. 迁移骨干，训练 224×224、batch 32 的分类模型。
3. 使用最佳检查点评估完整验证集和完整测试集，生成 Top-1、宏平均 F1、逐类指标、混淆矩阵及逐图预测。
4. 导出 ONNX；每类取一张验证图片，校验系统预处理与训练预处理一致、PyTorch 与 ONNX 概率一致。
5. 将候选模型打包至 `models/candidates/plantvillage-yolo26m`。

`ready_for_system_test` 表示训练、评估、导出及验证门槛已通过，仍需接入检查；不是系统验收完成。`quality_gate_failed` 或 `failed` 必须先排查，不能直接启用权重。

`keep_awake.py` 仅在当前训练进程存在时请求 Windows 避免自动睡眠，不修改全局电源方案，允许屏幕熄灭。电脑关机、手动睡眠、断电仍会中断训练。

## 恢复中断

先检查日志与 GPU，处理失败原因。不要在训练仍运行时重复启动。确认中断后：

```powershell
.\training\.venv\Scripts\python.exe -X utf8 -u .\training\resume_training.py
```

该命令核对进程创建时间，拒绝覆盖活动训练，并从 `last.pt` 恢复优化器与训练进度。训练已正常结束但评估或导出中断时，完成标记使流程跳过训练，重新执行评估和导出。

## 校验与接入本地系统

后端需要安装 `backend/requirements-inference.txt`。在项目根目录运行：

```powershell
.\backend\.venv\Scripts\python.exe -X utf8 .\training\deploy_model.py
```

默认只验证：校验模型摘要、完整评估报告、38 类顺序和质量门槛，再用临时数据库实际运行 ONNX、逐类图片上传、结果持久化、看板统计、删除以及异常请求。上传接口会重新编码 JPEG，比较基准使用相同保存像素。38 张接口样本的准确率只是联调观测，不能替代完整测试集成绩。

验证通过后配置版本化模型：

```powershell
.\backend\.venv\Scripts\python.exe -X utf8 .\training\deploy_model.py --activate
.\scripts\stop-dev.ps1
.\scripts\start-dev.ps1
```

启用脚本只更新 `backend/.env` 的 `MODEL_MANIFEST`，保留其他配置；旧值记录在 `.runtime/model-deployments`。模型发布到 `models/releases/<name>-<onnx摘要前12位>`，不同内容不能覆盖同一版本。`deployment.json` 表示配置已写入；重启后必须确认 `/api/health` 为 `model: ready`、`/api/models` 摘要一致。

前端使用 Chrome DevTools MCP 验证真实图片上传、类别、置信度、记录和模型管理页；保存测试证据后清理自己创建的测试记录。当前本地端口为前端 5173、后端 8000。这个流程针对现有本地系统，Docker 部署需要另外配置模型只读挂载和推理依赖。

## 测试命令

```powershell
.\training\.venv\Scripts\python.exe -m pytest .\training\test_workflow.py .\training\test_deployment.py -q
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q
Pop-Location
Push-Location frontend
npm.cmd run build
Pop-Location
```

`export_smoke.py` 可使用一份已经保存的轮次检查点，在 CPU 上提前验证 ONNX 兼容性。它不启用中间模型，也不代表最终精度。

模型仅覆盖 PlantVillage 的 14 种作物、38 类。低于配置阈值的结果提示人工复核；图片预测作物与所选作物不一致时拒绝保存为确定诊断。该数据的实验室背景与田间照片不同，不能把本数据集测试指标表述为田间识别能力。
