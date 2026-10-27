# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：QwenImageStudio（onedir，轻量，GUI 基础依赖）."""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

_icon = os.path.join("assets", "icon.ico")
_vinfo = os.path.join("assets", "version_info.txt")
_win_only = sys.platform.startswith("win")

hidden = (
    collect_submodules("ttkbootstrap")
    + collect_submodules("pip")  # 打包 exe 内置 pip，供依赖自检 --target 安装
    + [
        "qwen_image_studio.taglib",
        "qwen_image_studio.engine",
        "qwen_image_studio.ui",
        "qwen_image_studio.version_info",
    ]
)

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("src/qwen_image_studio", "qwen_image_studio"),
        ("data/tags.json", "data"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy.f2py", "scipy", "pandas", "PyQt5", "PySide2", "PyQt6", "PySide6"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="QwenImageStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=_icon if _win_only and os.path.exists(_icon) else None,
    version=_vinfo if _win_only and os.path.exists(_vinfo) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="QwenImageStudio",
)
