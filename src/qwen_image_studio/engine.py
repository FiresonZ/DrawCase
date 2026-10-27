"""核心推理引擎：依赖自检、HF 模型下载、diffusers 生成.

设计目标：
- 首次运行无需任何 AI 依赖，软件启动后按需自动安装（torch/diffusers/transformers 等）
- 从 HuggingFace 直接下载 Qwen-Image 系列模型（含 datamodelcc/Qwen-Image 等社区镜像仓库）
- 支持 GGUF 量化、CPU 生成（小模型自动回退）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from typing import Callable, List, Optional

from .version_info import appdata_dir

# 内置推荐模型仓库（均可从 HuggingFace 直接获取）
BUILTIN_MODELS = [
    {
        "id": "Qwen/Qwen-Image",
        "name": "Qwen-Image (官方 20B)",
        "type": "safetensors",
        "size": "约 40GB (FP16)",
        "note": "官方全量模型，效果最好，需要较大显存",
    },
    {
        "id": "Qwen/Qwen-Image-Lightning-4steps-V1.0",
        "name": "Qwen-Image Lightning (4步加速)",
        "type": "safetensors",
        "size": "约 40GB (FP16)",
        "note": "蒸馏加速版，4 步出图，速度快",
    },
    {
        "id": "cercina/qwen-image-gguf",
        "name": "Qwen-Image GGUF (量化版)",
        "type": "gguf",
        "size": "按量化等级 8~20GB",
        "note": "Q2~Q8 量化，低显存 / CPU 也可运行",
    },
    {
        "id": "QuantStack/Qwen-Image-Lightning-4steps-V1.0-GGUF",
        "name": "Lightning GGUF 量化 (4步)",
        "type": "gguf",
        "size": "按量化等级 8~20GB",
        "note": "加速版量化，速度+低显存兼得",
    },
]


def appdata() -> str:
    d = appdata_dir()
    os.makedirs(d, exist_ok=True)
    return d


def runtime_dir() -> str:
    """AI 依赖安装目录（pip --target），打包 exe 内也可用."""
    d = os.path.join(appdata(), "runtime")
    os.makedirs(d, exist_ok=True)
    return d


def ensure_runtime_path() -> None:
    """把依赖目录注入 sys.path（须在 import torch 等之前调用）."""
    rd = runtime_dir()
    if rd not in sys.path:
        sys.path.insert(0, rd)


def models_dir() -> str:
    d = os.path.join(appdata(), "models")
    os.makedirs(d, exist_ok=True)
    return d


def outputs_dir() -> str:
    d = os.path.join(appdata(), "outputs")
    os.makedirs(d, exist_ok=True)
    return d


def state_path() -> str:
    return os.path.join(appdata(), "state.json")


def load_state() -> dict:
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st: dict) -> None:
    try:
        with open(state_path(), "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------- 依赖自检

REQUIRED_PKGS = [
    "diffusers>=0.34.0",
    "transformers>=4.51.0",
    "accelerate>=1.0.0",
    "safetensors>=0.4.0",
    "sentencepiece",
    "protobuf",
    "gguf",
    "huggingface_hub>=0.26.0",
]


def _pip(args: List[str]) -> int:
    """在打包 exe 与开发模式下都可用的 pip 安装.

    - 开发模式: 直接用解释器自带 pip
    - 打包模式: 使用 PyInstaller 打入的 pip 模块, --target 装到用户数据目录
    """
    target = runtime_dir()
    full = ["install", "--quiet", "--target", target, "--upgrade", *args]
    try:
        from pip._internal.cli.main import main as pip_main  # type: ignore

        return pip_main(full)
    except Exception:
        return subprocess.call(
            [sys.executable, "-m", "pip", *full],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _has_nvidia_gpu() -> bool:
    try:
        out = subprocess.check_output(["nvidia-smi"], stderr=subprocess.DEVNULL, timeout=10)
        return b"NVIDIA" in out or b"nvidia" in out.lower()
    except Exception:
        return False


def is_python_available() -> bool:
    """打包 exe 内置运行时时恒为 True；开发模式下亦可用."""
    return True


def has_torch() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except Exception:
        return False


def torch_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():  # type: ignore[attr-defined]
            return "mps"
    except Exception:
        pass
    return "cpu"


def ensure_deps(log: Optional[Callable[[str], None]] = None) -> bool:
    """自动补齐 AI 运行依赖（装到用户数据目录，升级重装不重装）。返回是否成功."""

    def say(m: str) -> None:
        if log:
            log(m)

    ensure_runtime_path()
    missing = []
    for pkg in REQUIRED_PKGS:
        name = pkg.split(">=")[0].split("<")[0]
        try:
            __import__(name)
        except Exception:
            missing.append(pkg)
    if missing:
        say(f"正在安装依赖: {', '.join(missing)} ...")
        # 使用清华镜像加速国内下载
        idx = os.environ.get("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")
        rc = _pip(["-i", idx, *missing])
        if rc != 0:
            say("镜像源安装失败，尝试官方源...")
            rc = _pip(missing)
        if rc != 0:
            say("依赖安装失败，请检查网络或手动安装。")
            return False
    if not has_torch():
        gpu = _has_nvidia_gpu()
        if gpu:
            say("检测到 NVIDIA 显卡，正在安装 CUDA 版 PyTorch（约 2.5GB，请耐心等待）...")
            rc = _pip(["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu124"])
        else:
            say("未检测到 NVIDIA 显卡，安装 CPU 版 PyTorch（约 200MB）...")
            rc = _pip(["torch", "torchvision"])
        if rc != 0:
            say("PyTorch 安装失败，请检查网络后重试。")
            return False
    say("依赖自检完成。")
    return True


# ---------------------------------------------------------------- 模型下载


class HFDownloader:
    """带进度回调的 HF 下载器（用于 UI 显示进度条）."""

    def __init__(self) -> None:
        self._cancel = False
        self._p = 0.0

    def cancel(self) -> None:
        self._cancel = True

    def download(self, repo_id: str, log: Callable[[str], None], progress: Callable[[float], None]) -> bool:
        try:
            from huggingface_hub import snapshot_download
        except Exception:
            log("huggingface_hub 未就绪，请先完成依赖自检")
            return False
        self._cancel = False
        self._p = 0.0

        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=repo_id,
                local_dir=os.path.join(models_dir(), repo_id.replace("/", "__")),
                max_workers=4,
            )
            progress(1.0)
            log(f"模型下载完成: {repo_id}")
            return True
        except KeyboardInterrupt:
            return False
        except Exception as e:
            log(f"下载失败: {e}")
            return False


def list_local_models() -> List[str]:
    """扫描已下载到本地的模型（目录形式）."""
    out = []
    base = models_dir()
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            full = os.path.join(base, d)
            if os.path.isdir(full):
                out.append(d.replace("__", "/"))
    return out


def get_model_files(repo_id: str) -> List[str]:
    """列出模型目录内 .safetensors / .gguf 文件，供用户选择权重."""
    d = os.path.join(models_dir(), repo_id.replace("/", "__"))
    files = []
    if os.path.isdir(d):
        for root, _, names in os.walk(d):
            for n in names:
                if n.endswith((".safetensors", ".gguf")):
                    files.append(os.path.relpath(os.path.join(root, n), d))
    return sorted(files)


# ---------------------------------------------------------------- 生成


class Generator:
    """对 diffusers 管线的轻封装：懒加载、线程内生成."""

    def __init__(self) -> None:
        self._pipe = None
        self._repo: Optional[str] = None
        self._weight: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._pipe is not None

    def load(self, repo_id: str, weight: Optional[str], log: Callable[[str], None]) -> bool:
        """加载管线。weight 为模型目录内相对路径（gguf 用）."""
        with self._lock:
            if self._pipe is not None and self._repo == repo_id and self._weight == (weight or ""):
                return True
            if self._pipe is not None:
                log("释放旧模型内存...")
                del self._pipe
                self._pipe = None
            try:
                import torch  # type: ignore
                from diffusers import DiffusionPipeline  # type: ignore

                local = os.path.join(models_dir(), repo_id.replace("/", "__"))
                path = local if os.path.isdir(local) else repo_id
                dev = torch_device()
                log(f"加载模型: {path} (设备: {dev})")
                dtype = torch.float16 if dev == "cuda" else torch.float32

                # GGUF 权重：单独加载 transformer，再挂到官方基础管线
                if weight and weight.endswith(".gguf"):
                    from diffusers import (  # type: ignore
                        GGUFQuantizationConfig,
                        QwenImagePipeline,
                        QwenImageTransformer2DModel,
                    )

                    gguf_path = os.path.join(local, weight)
                    if not os.path.isfile(gguf_path):
                        log(f"GGUF 权重不存在: {gguf_path}")
                        return False
                    log(f"加载 GGUF transformer: {weight}（首次会自动补齐官方基础组件）")
                    transformer = QwenImageTransformer2DModel.from_single_file(
                        gguf_path,
                        quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
                        torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
                    )
                    pipe = QwenImagePipeline.from_pretrained(
                        "Qwen/Qwen-Image",
                        transformer=transformer,
                        torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
                    )
                else:
                    pipe = DiffusionPipeline.from_pretrained(
                        path,
                        torch_dtype=dtype,
                    )
                pipe.to(dev)
                if dev == "cuda":
                    pipe.enable_attention_slicing()
                self._pipe = pipe
                self._repo = repo_id
                self._weight = weight or ""
                log("模型加载完成")
                if "lightning" in repo_id.lower():
                    log("提示: Lightning 加速模型建议使用 步数=4、CFG=1.0")
                return True
            except Exception as e:
                log(f"模型加载失败: {e}")
                return False

    def generate(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        seed: int,
        log: Callable[[str], None],
        progress: Callable[[float], None],
    ) -> Optional[str]:
        """执行生成，返回保存的图片路径."""
        with self._lock:
            if self._pipe is None:
                log("模型未加载")
                return None
            try:
                import torch  # type: ignore

                gen = torch.Generator(device=torch_device()).manual_seed(seed)
                log(f"开始生成: {width}x{height}, {steps} 步, CFG {guidance}, 种子 {seed}")

                def _cb(pipe_obj, i, t, cbk):  # type: ignore[no-untyped-def]
                    progress((i + 1) / steps)
                    return cbk

                out = self._pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt or None,
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    generator=gen,
                    callback_on_step_end=_cb,
                )
                img = out.images[0]
                from datetime import datetime

                fn = datetime.now().strftime("img_%Y%m%d_%H%M%S_%f")[:-3] + ".png"
                path = os.path.join(outputs_dir(), fn)
                img.save(path)
                log(f"已保存: {path}")
                return path
            except Exception as e:
                log(f"生成失败: {e}")
                return None

    def unload(self) -> None:
        with self._lock:
            self._pipe = None
            try:
                import torch  # type: ignore
                import gc  # type: ignore

                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
