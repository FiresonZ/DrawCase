# QwenImageStudio · Qwen 镜像工坊

本地 Qwen-Image 生图工作台 —— 免环境配置、开箱即用、内置中文 Tag 库。

**作者**: FiresonZ <dev@gith.uk>

## 特性

- **零依赖门槛**：安装即用，AI 依赖（PyTorch / diffusers 等）由软件按需自动安装，设置页实时显示进度；已装则显示「已安装 ✓」
- **模型自管，不被升级覆盖**：从 HuggingFace 自行下载模型，放入安装目录 `models\QwenImage` 或 `models\SDXL`（也可在设置里添加任意自定义模型文件夹），软件自动扫描
- **双系列支持**：Qwen-Image 全量 / GGUF（自动补齐 2.1 或 1.0 基础组件）+ SDXL 系单文件整合包（含 V-Prediction 自动调度）
- **设置页手动切换模型系列**，下拉选择模型点「使用」
- **中文 Tag 库**：中英对照、分类浏览、搜索，双击插入提示词
- **升级覆盖安装**：依赖装在 `%LOCALAPPDATA%\QwenImageStudio\runtime`、模型在安装目录 `models\`（卸载标志 neveruninstall）、配置在 `%LOCALAPPDATA%`，升级重装全部保留
- **轻量现代化 UI**：暗色扁平界面，安装包小、启动快

## 使用

1. 下载 [Releases](https://github.com/FiresonZ/QwenImageStudio/releases) 中的 `QwenImageStudio-Setup-x.x.x.exe`，安装（支持直接覆盖升级旧版）
2. 启动 → 软件自动安装 AI 依赖（「设置」页有进度条；已安装则显示「已安装 ✓」）
3. 从 HuggingFace 下载模型，放入安装目录 `models\QwenImage`（Qwen-Image 系）或 `models\SDXL`（SDXL 系单文件整合包）；或在「设置」页添加自定义模型文件夹
4. 「设置」页选择模型系列 → 下拉选择模型 → 点「使用」→ 顶部「加载模型」
5. 在 Tag 库双击中文标签组好提示词 → 「开始生成」

## 构建（开发者）

Actions 页 → **Build Windows Setup (QwenImageStudio)** → 填写版本号、勾选「是否发布」：
- 仅构建：产生 Artifact 供下载验证
- 勾选发布：以该版本号打包并发布到 Releases

本地构建需 Windows + Inno Setup 6 + Python 3.11：

```bash
pip install -r requirements.txt
pyinstaller QwenImageStudio.spec --noconfirm
ISCC.exe installer\QwenImageStudio.iss
```

## 目录结构

```
src/qwen_image_studio/
  engine.py        # 依赖自检（进度）/ 本地模型扫描 / diffusers 生成
  taglib.py        # 内置中文 Tag 库（支持 tags_extra.csv 扩展）
  ui.py            # 主界面（ttkbootstrap，纯 ttk 深色回退）
  version_info.py  # 版本与作者信息
main.py            # exe 入口
installer/         # Inno Setup 脚本（升级覆盖安装，内置 models 模型文件夹）
.github/workflows/ # 手动触发打包 + 可选发布
```

## License

见 [LICENSE](LICENSE)。
