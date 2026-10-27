"""应用入口：QwenImageStudio.exe."""

import multiprocessing
import sys


def main() -> None:
    multiprocessing.freeze_support()  # PyInstaller 打包必需
    # 依赖安装目录注入 sys.path（必须在 import 任何 AI 库之前）
    from qwen_image_studio import engine

    engine.ensure_runtime_path()

    from qwen_image_studio.ui import main as ui_main

    ui_main()


if __name__ == "__main__":
    main()
