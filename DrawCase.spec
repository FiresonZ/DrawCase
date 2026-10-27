# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：DrawCase（onedir，轻量，GUI 基础依赖）."""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

_icon = os.path.join("assets", "icon.ico")
_vinfo = os.path.join("assets", "version_info.txt")
_win_only = sys.platform.startswith("win")

# pip 除 .py 还有运行时数据（_vendor/certifi/cacert.pem 等）：
# 只 collect_submodules 会漏掉这些文件，导致 exe 内所有 HTTPS 请求证书校验失败
_pip_data = collect_data_files("pip")
try:
    _pip_data += collect_data_files("certifi")
except Exception:
    pass

hidden = (
    collect_submodules("ttkbootstrap")
    + collect_submodules("pip")  # 打包 exe 内置 pip，供依赖自检 --target 安装
    + [
        "drawcase.taglib",
        "drawcase.engine",
        "drawcase.api_server",
        "drawcase.ui",
        "drawcase.version_info",
    ]
)

a = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("src/drawcase", "drawcase"),
        ("data/tags.json", "data"),
    ] + _pip_data,
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
    name="DrawCase",
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
    name="DrawCase",
)
