# QwenImageStudio · Qwen 镜像工坊

本地 Qwen-Image 生图工作台 —— 免环境配置、开箱即用、内置中文 Tag 库。

**作者**: FiresonZ <dev@gith.uk>

## 特性

- **零依赖门槛**：安装即用，AI 依赖（PyTorch / diffusers 等）由软件内置「依赖自检」按需自动安装
- **HuggingFace 一键下载**：内置官方与社区 Qwen-Image 模型（含 GGUF 量化版），支持断点续传
- **中文 Tag 库**：参考 diffusionWeb 打包版的常用标签，中英对照、分类浏览、搜索，双击插入提示词
- **升级覆盖安装**：模型、作品、配置保存在用户数据目录（`%LOCALAPPDATA%\QwenImageStudio`），直接运行新版安装包即可升级，数据不丢失
- **轻量现代化 UI**：暗色扁平界面，Tkinter 原生渲染，安装包小、启动快

## 使用

1. 下载 [Releases](https://github.com/FiresonZ/QwenImageStudio/releases) 中的 `QwenImageStudio-Setup-x.x.x.exe`
2. 安装并启动 → 软件自动完成依赖自检
3. 「模型管理」→ 选择模型下载（建议低配机器选 GGUF 量化版）
4. 「加载模型」→ 在 Tag 库双击中文标签组好提示词 → 「开始生成」

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
  engine.py        # 依赖自检 / HF 下载 / diffusers 生成
  taglib.py        # 内置中文 Tag 库（支持 tags_extra.csv 扩展）
  ui.py            # 主界面（ttkbootstrap，纯 ttk 深色回退）
  version_info.py  # 版本与作者信息
main.py            # exe 入口
installer/         # Inno Setup 脚本（升级覆盖安装）
.github/workflows/ # 手动触发打包 + 可选发布
```

## License

见 [LICENSE](LICENSE)。
