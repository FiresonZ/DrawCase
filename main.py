"""应用入口：QwenImageStudio.exe."""

import multiprocessing
import sys


def main() -> None:
    multiprocessing.freeze_support()  # PyInstaller 打包必需
    from qwen_image_studio.ui import main as ui_main

    ui_main()


if __name__ == "__main__":
    main()
