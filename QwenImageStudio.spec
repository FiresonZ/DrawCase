# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：QwenImageStudio（onedir，轻量，GUI 基础依赖）."""

import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

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
    icon="assets/icon.ico" if sys.platform.startswith("win") else None,
    version="assets/version_info.txt" if sys.platform.startswith("win") else None,
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
