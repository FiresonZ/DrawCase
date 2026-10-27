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
import time
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
        "id": "AtomicChat/Qwen-Image-2.1-Turbo-Uncensored-GGUF",
        "name": "Qwen-Image 2.1 Turbo 无审查 GGUF",
        "type": "gguf",
        "size": "按量化等级 4~16GB",
        "note": "8 步蒸馏加速；首次加载自动补齐 2.1 基础组件（文本编码器/VAE）",
    },
    {
        "id": "ShinoharaHare/WAI-NSFW-illustrious-SDXL-V14.0-V-Prediction",
        "name": "WAI illustrious V14 V-Pred (SDXL 动漫系)",
        "type": "single-file",
        "size": "单文件约 5.1GB",
        "note": "SDXL 系；可只下载仓库中最大的单文件 safetensors（含全部组件）",
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


# ---------------------------------------------------------------- HF 镜像源

HF_OFFICIAL = ""  # 官方源（默认）
HF_MIRROR = "https://hf-mirror.com"  # 国内镜像


def set_hf_endpoint(url: str) -> None:
    """切换 HF 站点（""=官方）。必须在首次 import huggingface_hub 前调用；已导入则热替换."""
    os.environ["HF_ENDPOINT"] = url
    st = load_state()
    st["hf_endpoint"] = url
    save_state(st)
    try:  # 已导入时热替换常量
        import huggingface_hub.constants as c  # type: ignore

        c.ENDPOINT = url.rstrip("/") if url else "https://huggingface.co"
    except Exception:
        pass


def get_hf_endpoint() -> str:
    return load_state().get("hf_endpoint", "")


def apply_saved_endpoint() -> None:
    set_hf_endpoint(get_hf_endpoint())


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

# 全局下载状态（主窗口「下载/设置」页展示）
_dl_state: dict = {
    "repo": None,
    "running": False,
    "pct": 0.0,
    "speed": 0,  # 字节/秒
    "msg": "",
    "ok": None,
}


def download_state() -> dict:
    return dict(_dl_state)


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def start_download(
    repo_id: str,
    log: Callable[[str], None],
    on_update: Callable[[dict], None],
    filename: Optional[str] = None,
) -> None:
    """启动后台下载（非阻塞）。filename 指定时只下载该单文件。进度通过 on_update 推送."""

    if _dl_state["running"]:
        log(f"已有下载任务进行中: {_dl_state['repo']}，请等待完成")
        on_update(dict(_dl_state))
        return

    def push(**kw: object) -> None:
        _dl_state.update(kw)
        on_update(dict(_dl_state))

    local = os.path.join(models_dir(), repo_id.replace("/", "__"))
    os.makedirs(local, exist_ok=True)
    stop = {"flag": False}
    target_file = filename  # 单文件下载目标（用于进度计算）

    def watcher(total: int) -> None:
        prev = 0
        # 单文件下载时只统计目标文件本身（含 .incomplete 临时文件）
        def walk_files():
            for root, _, fs in os.walk(local):
                for fn in fs:
                    yield os.path.join(root, fn)

        while not stop["flag"] and _dl_state["running"]:
            cur = 0
            for fp in walk_files():
                base = os.path.basename(fp)
                if target_file and base != target_file and not base.endswith(".incomplete"):
                    continue
                try:
                    cur += os.path.getsize(fp)
                except OSError:
                    pass
            pct = min(0.99, cur / total) if total > 0 else 0.0
            push(pct=pct, speed=cur - prev, msg=f"{_fmt_bytes(cur)} / {_fmt_bytes(total)}")
            prev = cur
            time.sleep(1)

    def run() -> None:
        label = f"{repo_id} [{filename}]" if filename else repo_id
        push(repo=repo_id, running=True, ok=None, pct=0.0, speed=0, msg="准备下载…")
        log(f"开始下载: {label}（支持断点续传）")
        try:
            from huggingface_hub import HfApi, hf_hub_download, snapshot_download

            total = 0
            try:
                info = HfApi().model_info(repo_id, files_metadata=True)
                for f in (info.siblings or []):
                    if filename is None or f.rfilename == filename:
                        total += (f.size or 0)
            except Exception:
                pass
            t = threading.Thread(target=watcher, args=(total,), daemon=True)
            t.start()
            if filename:
                hf_hub_download(repo_id=repo_id, filename=filename, local_dir=local)
            else:
                snapshot_download(repo_id=repo_id, local_dir=local, max_workers=4)
            push(running=False, ok=True, pct=1.0, speed=0, msg="下载完成")
            log(f"下载完成: {label}")
        except Exception as e:
            push(running=False, ok=False, speed=0, msg=f"下载失败: {e}")
            log(f"下载失败: {e}")
        finally:
            stop["flag"] = True

    threading.Thread(target=run, daemon=True).start()


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


def _load_single_file_pipe(fpath: str, dtype: object, log: Callable[[str], None]) -> object:
    """加载单文件整合模型（SDXL / SD1.x / SD2.x）."""
    from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline  # type: ignore

    name = os.path.basename(fpath).lower()
    try:
        log("单文件整合模型，按 SDXL 管线加载…")
        pipe = StableDiffusionXLPipeline.from_single_file(fpath, torch_dtype=dtype)
    except Exception as e:
        log(f"SDXL 管线加载失败（{e}），回退通用 SD 管线…")
        pipe = StableDiffusionPipeline.from_single_file(fpath, torch_dtype=dtype)
    if "v-pred" in name or "v_prediction" in name:
        try:
            from diffusers import EulerDiscreteScheduler  # type: ignore

            pipe.scheduler = EulerDiscreteScheduler.from_config(
                pipe.scheduler.config,
                prediction_type="v_prediction",
                rescale_betas_zero_snr=True,
            )
            log("已启用 V-Prediction 调度（建议 CFG 1.5~2.5、步数 20~30）")
        except Exception as e:
            log(f"V-Prediction 配置失败: {e}")
    return pipe


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
                has_index = os.path.isfile(os.path.join(local, "model_index.json"))

                # 未指定权重且仓库无 diffusers 结构时，自动选最大的整合单文件
                if not weight and not has_index and os.path.isdir(local):
                    cands = [f for f in get_model_files(repo_id) if "/" not in f]
                    if cands:
                        weight = max(cands, key=lambda f: os.path.getsize(os.path.join(local, f)))
                        log(f"自动选择整合文件: {weight}")

                # GGUF 权重：单独加载 transformer，再挂到对应版本的基础管线
                if weight and weight.endswith(".gguf"):
                    from diffusers import (  # type: ignore
                        GGUFQuantizationConfig,
                        QwenImagePipeline,
                        QwenImageTransformer2DModel,
                    )

                    # 按模型版本自动匹配基础组件仓库（文本编码器 / VAE）
                    tag = f"{repo_id} {weight}".lower()
                    if "2.1" in tag:
                        base = "Qwen/Qwen-Image-2.1"
                    elif "lightning" in tag and "gguf" not in repo_id.lower():
                        base = "Qwen/Qwen-Image"
                    else:
                        base = "Qwen/Qwen-Image"
                    gguf_path = os.path.join(local, weight)
                    if not os.path.isfile(gguf_path):
                        log(f"GGUF 权重不存在: {gguf_path}")
                        return False
                    log(f"加载 GGUF transformer: {weight}")
                    log(f"基础组件仓库: {base}（文本编码器 / VAE，首次加载自动补齐）")
                    transformer = QwenImageTransformer2DModel.from_single_file(
                        gguf_path,
                        quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
                        torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
                    )
                    pipe = QwenImagePipeline.from_pretrained(
                        base,
                        transformer=transformer,
                        torch_dtype=torch.bfloat16 if dev == "cuda" else torch.float32,
                    )
                else:
                    # 顶层单文件整合（.safetensors 无子目录路径）→ 单文件加载
                    if weight and "/" not in weight and weight.endswith(".safetensors") and os.path.isfile(os.path.join(local, weight)):
                        pipe = _load_single_file_pipe(os.path.join(local, weight), dtype, log)
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
                if "turbo" in repo_id.lower():
                    log("提示: Turbo 蒸馏模型建议使用 步数=8、CFG=1.0")
                if "v-pred" in repo_id.lower() or "v_prediction" in repo_id.lower():
                    log("提示: V-Prediction 模型建议使用 CFG 1.5~2.5、步数 20~30")
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
