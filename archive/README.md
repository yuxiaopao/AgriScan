# 完整项目归档

2026 年 11 月 11 日公开归档包含项目源码、现有测试、环境依赖、训练数据、40 轮检查点、模型、安装包、历史验收记录、设计和答辩交付材料。

源码、测试和交付材料可在 `main` 浏览。完整工作文件和大文件位于 [GitHub Releases](https://github.com/yuxiaopao/AgriScan/releases/tag/project-archive-20261111)，以 512 MiB 分卷保存。Releases 的总容量和下载带宽没有配额上限，单个附件须小于 2 GiB。本次大文件使用 Releases 保存。[GitHub 官方说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)

## 下载和校验

`release-manifest.json` 列出分卷顺序、文件大小、SHA256 和下载地址。`file-index.json.gz` 附件列出完整归档中的原始路径、大小、SHA256 和脱敏标记。重复内容在归档中使用硬链接保存，恢复后仍保留各自路径。

使用 Python 3.12 或更高版本，在仓库根目录执行以下命令。目标目录须为空，下载缓存和解压结果需要分别预留空间。

```powershell
python scripts/restore-archive.py --output ..\AgriScan-public-snapshot
```

已经下载的分卷会先校验再复用。仅下载和校验时添加 `--download-only`。也可以按清单从 Releases 下载分卷，放入 `.archive-downloads/` 后执行同一命令。

检测模型、分类模型和 Android 测试包同时提供独立附件。检测模型 `detector-model.onnx` 恢复到 `models/candidates/user-detect-fafc2bb3ce9e/model.onnx`，其 SHA256 须与同目录清单一致。

## 记录位置

| 路径 | 内容 |
| --- | --- |
| `backend/tests/`、`shared/tests/`、`training/test_*.py` | 现有自动化测试源码 |
| `archive/verification/` | 历史检查脚本、测试 XML、部署和浏览器验收记录的公开副本 |
| `archive/training/`、`archive/training-runs/` | 训练状态、完整评估、预测 CSV、曲线和混淆矩阵 |
| `archive/environment/` | 实际 Python 依赖快照、操作系统和 Node.js 工具版本 |
| `.env.example`、各端 `.env.example`、锁文件、Docker 配置 | 环境重建配置 |
| `deliverables/`、`design/` | 答辩、报告、演示、照片、设计草稿和生成记录 |
| Releases 完整归档中的 `datasets/`、`runs/`、`models/` | 原始数据、数据划分、逐轮权重、导出模型 |
| Releases 完整归档中的 `.runtime/` | 经过过滤和脱敏的历史测试、构建与工作文件 |

历史记录保留各自生成时的结果。失败记录及随后的修复记录一起保留，归档操作本身没有重新执行这些历史测试。`archive/verification/` 内的部署、清理和修补脚本属于历史操作记录，使用前应检查路径、服务地址和作用范围。脱敏副本中的 `REDACTED_*` 字段需要自行配置。

实际 `.env`、API 密钥、登录令牌、账号密码、数据库、浏览器会话及签名私钥已从公开归档中排除或脱敏。依赖安装目录、工具链安装缓存、下载中的依赖包、临时日志和进程文件使用环境清单重建。原始本地文件保留。

数据集来源及其 `cc-by-sa-3.0` 标记保留在 `datasets/plantvillage/source/README.md`，来源版本和下载哈希见 `training/config.json`。字体、第三方代码、数据集和模型保留各自的来源与许可说明。
