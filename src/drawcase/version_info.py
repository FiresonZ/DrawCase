"""单文件内置版本信息（避免依赖外部资源文件，便于 exe 化）."""

APP_NAME = "DrawCase"
APP_NAME_ZH = "DrawCase"
AUTHOR = "FiresonZ"
AUTHOR_EMAIL = "dev@gith.uk"
HOMEPAGE = "https://github.com/FiresonZ/DrawCase"
VERSION = "0.1.0"

# Tag 库远程更新（提交在仓库 data/tags.json，经 GitHub 代理加速下载）
GH_REPO = "FiresonZ/DrawCase"
GH_BRANCH = "main"

# 首选项 / 用户数据存放目录（升级覆盖安装时保留）
import os
import sys


def appdata_dir() -> str:
    """返回用户数据目录：使用 %LOCALAPPDATA%/DrawCase（Windows）或 ~/.drawcase。"""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "DrawCase")
    return os.path.join(os.path.expanduser("~"), ".drawcase")
