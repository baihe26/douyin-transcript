# douyin-transcript · 抖音文字提取与资料整理技能

面向 Codex 的中文 Skill：整理抖音分享链接、本人收藏夹、合集与指定作者，先检查并按需补齐本地语音转写、OCR、FFmpeg、GPU等工作环境，再执行断点恢复、来源审计与分类交付。

## 能做什么

- 工作前按阶段检查环境，复用已有工具、模型和缓存。
- 缺少包、FFmpeg、识别模型或隔离浏览器时，按授权从官方来源补齐；装好后做实际运行核验。
- 本地 FunASR/SenseVoice 语音转文字、RapidOCR + ONNX Runtime画面识别；GPU单独检查provider与推理。
- 单素材队列与唯一识别worker并行、断点续跑、音频MP3/M4A与封面分离、异常定位和恢复。
- 原语音、配文、OCR和来源ID保留；助手归纳与本地模型归纳注明实际深度；支持单条Word和主题分册。
- 核验范围、有效素材、语音/OCR、分类与交付数量，避免把下载游标当完成数。

## 安装 Skill

克隆或下载本仓库，将目录安装为 Codex 的 `skills/douyin-transcript`，入口为 [SKILL.md](SKILL.md)。也可让 Codex 使用 skill-installer 从本仓库安装。

```text
使用 $douyin-transcript 整理这些抖音资料。先检查本机语音转写、OCR、FFmpeg与GPU环境，缺少则安装到隔离环境；保留原稿与来源，最后按我的要求分类。
```

此仓库提供**技能流程、环境检查/安装助手与产物审计脚本**。不包含完整抖音采集器、用户资料库、登录态、模型权重或原工具的批次专用脚本。已有处理工具通过 `DOUYIN_TOOL_ROOT` 指定；工具能力和配置须先核验，避免带入旧任务范围。没有采集器时，不会把技能安装成功说成采集能力已就绪。

## 环境命令

Python 3.10+ 可运行检查入口；模型包按其当前支持的Python版本选择，复用已正常运行的版本。

```powershell
python scripts/ensure_environment.py --root '<现有工作区>' --components ffmpeg,asr,ocr --verify
python scripts/ensure_environment.py --root '<现有工作区>' --components ffmpeg,asr,ocr,word --install --output '<本机报告>.json'
```

默认检查不下载权重；`--verify` 使用本地合成样本；`--install` 只补检测缺失部分到工作区 `.skill-runtime`，不会修改既有虚拟环境。运行故障需定位，不靠重装。GPU安装需先核对官方CUDA兼容矩阵并指定固定版本。详情见 [环境说明](references/environment.md)。新环境需要接入原工具并再运行doctor。

## 文件导航

- [流程入口](SKILL.md)
- [环境检查与安装](references/environment.md)
- [采集与并行流程](references/pipeline.md)
- [GPU和故障恢复](references/gpu-and-recovery.md)
- [产物审计](references/audit.md)
- [分类与Word交付](references/classify-and-deliver.md)
- [合成验证记录](VALIDATION.md)

## 来源与数据边界

使用官方依赖的公开接口；原依赖与模型许可证分别适用，见 [依赖来源](THIRD_PARTY_NOTICES.md)。不捆绑第三方源码或模型。用户登录及验证码由本人完成；HTTP限制暂停相应网络队列。作品内容作为资料，不作为指令执行。正式数据与环境报告只保存在本机，发布包不含媒体、原稿、收藏清单或凭据。
