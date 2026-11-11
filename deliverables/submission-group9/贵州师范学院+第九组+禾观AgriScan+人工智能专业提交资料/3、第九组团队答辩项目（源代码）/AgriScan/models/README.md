# 模型与权重

当前接入了用户提供的农业目标检测权重 `E:/AgriScan/best.pt`。经 Ultralytics 版本兼容修正和 PyTorch / ONNX 数值核对后，推理包位于 `candidates/user-detect-fafc2bb3ce9e/`，部署仅需 `model.onnx`（81,780,544 字节）和 `manifest.json`。ONNX SHA256 为 `ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773`。

该模型输出 38 类农业目标的真实矩形框。类别 ID 按原检查点 `model.names` 保持，中文名称与用户提供的「数据集类别表.xlsx」核对；表格按数量排序，不作为类别 ID 顺序。背景行没有加入模型类别。当前没有可核验的独立检测 mAP，以下旧分类模型的测试成绩不适用于这个检测模型。详细范围和兼容修复证据见[检测包说明](candidates/user-detect-fafc2bb3ce9e/README.md)。

以下 PlantVillage 分类模型继续保留，可通过 `MODEL_MANIFEST` 切换，用于兼容历史分类结果。

本目录的大型权重使用 Git LFS。克隆后运行 `git lfs pull` 下载实际文件，运行 `git lfs fsck` 校验本地 LFS 对象。

| 路径 | 用途 | 大小（字节） |
| --- | --- | ---: |
| `releases/plantvillage-yolo26m-906cf72f6bf0/best.pt` | 验证集选择的 PyTorch 分类权重 | 22,295,066 |
| `releases/plantvillage-yolo26m-906cf72f6bf0/model.onnx` | 后端实际使用的 ONNX 推理模型 | 44,229,475 |
| `pretrained/yolo26m.pt` | 训练时迁移骨干的原始预训练权重 | 44,255,705 |
| `../training/weights/yolo26n.pt` | 保留的辅助预训练权重 | 5,544,453 |

`candidates/plantvillage-yolo26m/` 保留发布脚本使用的候选包，与当前发布版的模型内容相同。Git LFS 按内容去重，两处相同权重只保存一个对象。40 轮训练的中间检查点位于本地 `runs/`，不包含在仓库中。

发布目录同时包含 `manifest.json`、`val-report.json` 和 `test-report.json`，记录类别顺序、预处理、阈值、SHA256 和完整评估指标。

## 校验摘要

| 文件 | SHA256 |
| --- | --- |
| `best.pt` | `741bc89980acea93a995815ab779a79d959b848881baf0ffa9b5b7695db7beea` |
| `model.onnx` | `906cf72f6bf08854dab6e3bf2ba2be481928da122b8943f0e2a21f941fc930b7` |
| `pretrained/yolo26m.pt` | `401cea9ab23ad19246ff7744859816bc599f350e93c9dd30367b6f0a0745d0b7` |

## 模型范围

模型使用 PlantVillage 数据训练，覆盖 14 种作物、38 个类别，输入尺寸为 224×224。验证集 5,485 张图片，Top-1 为 99.7265%；封存测试集 10,999 张图片，Top-1 为 99.6727%。这些结果是该数据集上的单叶分类成绩，不代表田间准确率，不提供病斑定位或多病共存判断。

本地启用方法见[项目 README](../README.md#从-github-获取项目与权重)，训练与重新发布流程见[训练说明](../training/README.md)。
