"""核心推理引擎：依赖自检（带进度）、本地模型扫描、diffusers 生成.

设计目标：
- 首次运行无需任何 AI 依赖，软件启动后按需自动安装（torch/diffusers/transformers 等），
  安装过程实时显示进度；已安装则直接显示「已安装」
- 模型不由软件下载：用户从 HuggingFace 自行下载后放入模型文件夹（安装目录 models/
  下按系列分 QwenImage / SDXL，或设置里添加的自定义文件夹），软件扫描后在设置里选择
- 支持模型系列：Qwen-Image（全量 / GGUF）与 SDXL 系（单文件整合包）
- 升级覆盖安装不影响：依赖装在 %LOCALAPPDATA% 运行时目录，模型由用户自管
"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from typing import Callable, List, Optional

from .version_info import appdata_dir

# ---------------------------------------------------------------- 基础目录


def appdata() -> str:
    d = appdata_dir()
    os.makedirs(d, exist_ok=True)
    return d


def runtime_dir() -> str:
    """AI 依赖安装目录（pip --target），打包 exe 内也可用；升级重装不覆盖."""
    d = os.path.join(appdata(), "runtime")
    os.makedirs(d, exist_ok=True)
    return d


def ensure_runtime_path() -> None:
    """把依赖目录注入 sys.path（须在 import torch 等之前调用）."""
    rd = runtime_dir()
    if rd not in sys.path:
        sys.path.insert(0, rd)


def outputs_dir() -> str:
    d = os.path.join(appdata(), "outputs")
    os.makedirs(d, exist_ok=True)
    return d


def install_dir() -> str:
    """程序安装目录：打包后为 exe 所在目录，开发模式为项目根目录."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


# ---------------------------------------------------------------- HF 镜像源
# GGUF 模型首次加载时仍需联网补齐官方基础组件（文本编码器 / VAE），故保留源切换

HF_OFFICIAL = ""  # 官方源（默认）
HF_MIRROR = "https://hf-mirror.com"  # 国内镜像


def set_hf_endpoint(url: str) -> None:
    """切换 HF 站点（""=官方）。持久化保存；已导入 hub 时热替换."""
    os.environ["HF_ENDPOINT"] = url
    st = load_state()
    st["hf_endpoint"] = url
    save_state(st)
    try:
        import huggingface_hub.constants as c  # type: ignore

        c.ENDPOINT = url.rstrip("/") if url else "https://huggingface.co"
    except Exception:
        pass


def get_hf_endpoint() -> str:
    return load_state().get("hf_endpoint", "")


def apply_saved_endpoint() -> None:
    set_hf_endpoint(get_hf_endpoint())


# ---------------------------------------------------------------- 模型系列与文件夹

FAMILIES = {"qwen": "QwenImage", "sdxl": "SDXL"}
FAMILY_LABELS = {"qwen": "Qwen-Image 系", "sdxl": "SDXL 系"}


def get_family() -> str:
    return load_state().get("model_family", "qwen")


def set_family(family: str) -> None:
    st = load_state()
    st["model_family"] = family
    save_state(st)


def builtin_model_root(family: Optional[str] = None) -> str:
    """安装目录内置模型文件夹（用户手动放入模型即可）."""
    fam = family or get_family()
    d = os.path.join(install_dir(), "models", FAMILIES.get(fam, "QwenImage"))
    os.makedirs(d, exist_ok=True)
    return d


def custom_model_dirs() -> List[str]:
    return [p for p in load_state().get("model_dirs", []) if os.path.isdir(p)]


def add_model_dir(path: str) -> None:
    st = load_state()
    dirs = st.get("model_dirs", [])
    if path not in dirs:
        dirs.append(path)
    st["model_dirs"] = dirs
    save_state(st)


def remove_model_dir(path: str) -> None:
    st = load_state()
    st["model_dirs"] = [p for p in st.get("model_dirs", []) if p != path]
    save_state(st)


def _weight_ext(name: str) -> bool:
    return name.lower().endswith((".safetensors", ".gguf"))


def scan_models(family: Optional[str] = None) -> List[dict]:
    """扫描模型文件夹，返回 [{name, path, kind}].

    kind:
      - diffusers : 含 model_index.json 的标准目录
      - file      : 单个权重文件（整合 safetensors / gguf）
      - folder    : 含权重文件的普通目录（自动挑最大权重）
    扫描范围：内置模型文件夹及其一级子目录 + 用户自定义文件夹。
    """
    fam = family or get_family()
    roots = [builtin_model_root(fam)]
    roots += custom_model_dirs()
    out: List[dict] = []
    seen = set()

    def add(name: str, path: str, kind: str) -> None:
        if path not in seen:
            seen.add(path)
            out.append({"name": name, "path": path, "kind": kind})

    for root in roots:
        if not os.path.isdir(root):
            continue
        for entry in os.scandir(root):
            if entry.is_file() and _weight_ext(entry.name):
                add(os.path.splitext(entry.name)[0], entry.path, "file")
            elif entry.is_dir():
                d = entry.path
                if os.path.isfile(os.path.join(d, "model_index.json")):
                    add(entry.name, d, "diffusers")
                    continue
                w = _largest_weight(d)
                if w:
                    add(entry.name, d, "folder")
    # 去重同名：后扫到的自定义文件夹可能重复
    return out


def _largest_weight(d: str, depth: int = 2) -> Optional[str]:
    """目录内最大的权重文件（含一层子目录，diffusers 分件也算）."""
    best: Optional[str] = None
    best_size = -1
    count = 0
    for dirpath, dirnames, filenames in os.walk(d):
        depth_now = dirpath[len(d):].count(os.sep)
        if depth_now >= depth:
            dirnames[:] = []
            continue
        for fn in filenames:
            if _weight_ext(fn):
                count += 1
                p = os.path.join(dirpath, fn)
                try:
                    sz = os.path.getsize(p)
                except OSError:
                    continue
                if sz > best_size:
                    best_size = sz
                    best = p
    if count == 0:
        return None
    return best


def get_active_model() -> Optional[dict]:
    return load_state().get("active_model")


def set_active_model(entry: dict) -> None:
    st = load_state()
    st["active_model"] = {"name": entry["name"], "path": entry["path"]}
    save_state(st)


# ---------------------------------------------------------------- LoRA


def lora_root() -> str:
    d = os.path.join(install_dir(), "models", "LoRA")
    os.makedirs(d, exist_ok=True)
    return d


def scan_loras() -> List[dict]:
    """扫描 LoRA 文件（models\\LoRA 及自定义文件夹，一层）."""
    roots = [lora_root()] + custom_model_dirs()
    out: List[dict] = []
    seen = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for entry in os.scandir(root):
            if entry.is_file() and entry.name.lower().endswith(".safetensors"):
                if entry.path not in seen:
                    seen.add(entry.path)
                    out.append({"name": os.path.splitext(entry.name)[0], "path": entry.path})
            elif entry.is_dir():
                w = _largest_weight(entry.path, depth=1)
                if w and w not in seen:
                    seen.add(w)
                    out.append({"name": entry.name, "path": w})
    return out


# ---------------------------------------------------------------- 依赖自检

REQUIRED_PKGS = [
    "diffusers>=0.34.0",
    "transformers>=4.51.0,<5",  # 5.x 与 diffusers 管线不兼容，锁 4.x
    "accelerate>=1.0.0",
    "safetensors>=0.4.0",
    "sentencepiece",
    "protobuf",
    "gguf",
    "huggingface_hub>=0.26.0,<1.0",  # transformers 4.x 要求 hub < 1
]


def _dist_name(spec: str) -> str:
    """从包声明（如 transformers>=4.51.0,<5）取发行包名."""
    for sep in (">=", "<=", "==", "~=", "!=", ">", "<"):
        if sep in spec:
            return spec.split(sep)[0].strip()
    return spec.strip()


def _import_name(spec: str) -> str:
    """发行包名 → 实际 import 名字（protobuf 的模块名是 google.protobuf）."""
    name = _dist_name(spec).lower()
    return {"protobuf": "google.protobuf"}.get(name, name)


# 国内 PyPI 镜像表（自动依次尝试，直到成功）
PIP_MIRRORS = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",      # 清华
    "https://mirrors.aliyun.com/pypi/simple",         # 阿里云
    "https://mirrors.cloud.tencent.com/pypi/simple",  # 腾讯云
    "https://mirrors.ustc.edu.cn/pypi/simple",        # 中科大
    "https://pypi.org/simple",                        # 官方
]


def detect_system_proxy() -> str:
    """自动搜寻代理：Windows 系统代理（注册表）→ 环境变量. 返回代理 URL 或空串."""
    if sys.platform.startswith("win"):
        try:
            import winreg  # type: ignore

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if enable:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
                if server:
                    if "=" not in server:  # 形如 127.0.0.1:7890
                        return f"http://{server}"
                    for part in server.split(";"):  # 形如 http=..;https=..
                        k, _, v = part.partition("=")
                        if k.lower() in ("http", "https") and v:
                            return ("" if v.startswith("http") else "http://") + v
        except Exception:
            pass
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    )


def _apply_proxy(log: Callable[[str], None]) -> None:
    p = detect_system_proxy()
    if p:
        os.environ.setdefault("HTTP_PROXY", p)
        os.environ.setdefault("HTTPS_PROXY", p)
        log(f"已自动使用系统代理: {p}")


def ensure_deps(
    log: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[str, float], None]] = None,
) -> bool:
    """自动补齐 AI 运行依赖（装到用户数据目录，升级重装不重装）。返回是否成功."""

    def say(m: str) -> None:
        if log:
            log(m)

    def prog(name: str, frac: float) -> None:
        if progress:
            progress(name, frac)

    ensure_runtime_path()
    _apply_proxy(log)
    st = deps_status()
    if st["libs"] and st["torch"]:
        say("所有 AI 依赖已安装 ✓（如需更换 GPU/CPU 版 torch 可手动处理）")
        prog("PyTorch", 1.0)
        return True

    if not st["libs"]:
        missing = []
        for pkg in REQUIRED_PKGS:
            try:
                __import__(_import_name(pkg))
            except Exception:
                missing.append(pkg)
        say(f"正在安装依赖库: {', '.join(missing)} ...")
        rc = _install_with_mirrors(missing, lambda f: prog("依赖库", f), say) if missing else 0
        if rc != 0:
            say("依赖安装失败，请检查上方错误信息或手动安装。")
            return False

    if not has_torch():
        gpu = _has_nvidia_gpu()
        if gpu:
            say("检测到 NVIDIA 显卡，正在安装 CUDA 版 PyTorch（约 2.5GB，请耐心等待）...")
            rc = _pip(
                ["torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu124"],
                progress=lambda f: prog("PyTorch", f),
                log=say,
            )
        else:
            say("未检测到 NVIDIA 显卡，安装 CPU 版 PyTorch（约 200MB）...")
            rc = _install_with_mirrors(["torch", "torchvision"], lambda f: prog("PyTorch", f), say)
        if rc != 0:
            say("PyTorch 安装失败，请检查网络后重试。")
            return False
    prog("PyTorch", 1.0)
    say("依赖自检完成 ✓")
    return True


def _install_with_mirrors(
    args: List[str],
    progress: Optional[Callable[[float], None]],
    log: Callable[[str], None],
) -> int:
    """按镜像表依次安装，全部失败则返回非零."""
    rc = 1
    for i, idx in enumerate(PIP_MIRRORS):
        log(f"使用镜像源 ({i + 1}/{len(PIP_MIRRORS)}): {idx}")
        rc = _pip(["-i", idx, *args], progress=progress, log=log)
        if rc == 0:
            # 新装到 runtime 目录后刷新导入缓存，避免 import 拿到旧的模块列表
            import importlib

            importlib.invalidate_caches()
            ensure_runtime_path()
            return 0
        log(f"  可达性探测: {_probe(idx)}")
        log("该源不可用，尝试下一个…")
    return rc


def _probe(url: str) -> str:
    """探测镜像可达性，返回简短结论（用于区分网络问题与 pip 自身问题）."""
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "DrawCase"})
        with urllib.request.urlopen(req, timeout=8, context=ssl.create_default_context()) as r:
            return f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


class _ProgressCapture:
    """捕获 pip 输出：解析 tqdm 百分比，同时保留错误行用于失败诊断."""

    _NOISE = ("collecting ", "downloading ", "using cached ", "looking in indexes",
              "requirement already satisfied", "━", "|██", "获取中")

    def __init__(self, cb: Optional[Callable[[float], None]] = None) -> None:
        self.cb = cb
        self.last = 0.0
        self.lines: List[str] = []

    def write(self, s: str) -> int:
        if self.cb:
            try:
                for m in re.finditer(r"(\d{1,3})%", s):
                    v = int(m.group(1)) / 100.0
                    if v >= self.last:
                        self.last = v
                        self.cb(min(0.99, v))
            except Exception:
                pass
        for ln in s.replace("\r", "\n").split("\n"):
            ln = ln.strip()
            if ln:
                self.lines.append(ln)
                if len(self.lines) > 400:  # 只保留尾部，防止超长输出吃内存
                    del self.lines[:200]
        return len(s)

    def error_lines(self, limit: int = 12) -> List[str]:
        """挑出最能说明失败原因的行."""
        keys = ("error", "错误", "could not", "no matching", "ssl", "certificate",
                "proxy", "timeout", "timed out", "connection", "failed", "无法",
                "失败", "denied", "retrying")
        picked = [ln for ln in self.lines if any(k in ln.lower() for k in keys)]
        if not picked:
            picked = [ln for ln in self.lines
                      if not ln.lower().startswith(self._NOISE)]
        return (picked or self.lines)[-limit:]

    def flush(self) -> None:
        pass


def _ensure_ca_bundle() -> None:
    """确保 TLS 根证书可用：打包 exe 内 pip 自带的 certifi 数据未收集时会全部 HTTPS 失败."""
    if os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("PIP_CERT"):
        return
    for mod in ("certifi", "pip._vendor.certifi"):
        try:
            m = __import__(mod, fromlist=["where"])
            p = m.where()
        except Exception:
            continue
        if p and os.path.isfile(p):
            os.environ["REQUESTS_CA_BUNDLE"] = p
            os.environ.setdefault("SSL_CERT_FILE", p)
            return


def _pip(
    args: List[str],
    progress: Optional[Callable[[float], None]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> int:
    """在打包 exe 与开发模式下都可用的 pip 安装（--target 装到用户数据目录）."""
    target = runtime_dir()
    _ensure_ca_bundle()
    full = [
        "install", "--no-input", "--disable-pip-version-check",
        "--no-warn-script-location", "--timeout", "30", "--retries", "2",
        "--progress-bar", "on", "--target", target, "--upgrade", *args,
    ]
    try:
        from pip._internal.cli.main import main as pip_main  # type: ignore
    except Exception as e:
        if getattr(sys, "frozen", False):
            # 打包后 sys.executable 是本程序，绝不能再拿它跑 -m pip（会递归启动自己）
            if log:
                log(f"内置 pip 不可用：{e}")
            return 1
        return subprocess.call([sys.executable, "-m", "pip", *full])

    cap = _ProgressCapture(progress)
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = cap, cap  # type: ignore[assignment]
    rc = 1
    try:
        r = pip_main(full)
        rc = 0 if r is None else int(r)
    except SystemExit as e:  # 部分 pip 版本以 SystemExit 退出
        code = e.code
        rc = 0 if code in (None, 0) else (code if isinstance(code, int) else 1)
    except Exception as e:
        cap.write(f"pip 运行异常: {type(e).__name__}: {e}\n")
        rc = 1
    finally:
        sys.stdout, sys.stderr = old_out, old_err  # type: ignore[assignment]

    if rc != 0 and log:
        # 把 pip 的真实错误暴露到界面日志，否则只看到"该源不可用"无从排查
        for ln in cap.error_lines():
            log("  " + ln)
    return rc


def _has_nvidia_gpu() -> bool:
    try:
        out = subprocess.check_output(["nvidia-smi"], stderr=subprocess.DEVNULL, timeout=10)
        return b"NVIDIA" in out or b"nvidia" in out.lower()
    except Exception:
        return False


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


def deps_status() -> dict:
    """检查依赖状态：{"libs": bool, "torch": bool}."""
    libs = True
    for pkg in REQUIRED_PKGS:
        try:
            __import__(_import_name(pkg))
        except Exception:
            libs = False
            break
    return {"libs": libs, "torch": has_torch()}


# ---------------------------------------------------------------- Tag 库远程更新

# GitHub 代理表（ghproxy 系），依次尝试；空串为直连 raw.githubusercontent.com
GH_PROXIES = [
    "",
    "https://ghproxy.net",
    "https://gh-proxy.com",
    "https://ghfast.top",
    "https://ghproxy.cc",
    "https://mirror.ghproxy.com",
]


def tags_remote_path() -> str:
    return os.path.join(appdata(), "tags_remote.json")


def local_tag_version() -> int:
    """当前生效的 Tag 库版本（远程更新过则取远程版本，否则内置版本）."""
    import json as _json

    try:
        with open(tags_remote_path(), "r", encoding="utf-8") as f:
            return int(_json.load(f).get("version", 0))
    except Exception:
        from . import taglib

        return taglib.BUILTIN_VERSION


def update_tags_from_github(log: Callable[[str], None]) -> bool:
    """经 GitHub 代理表下载仓库 data/tags.json 更新本地 Tag 库."""
    import json as _json
    import urllib.request

    from . import taglib
    from .version_info import GH_BRANCH, GH_REPO

    raw = f"https://raw.githubusercontent.com/{GH_REPO}/{GH_BRANCH}/data/tags.json"
    _apply_proxy(log)
    for prefix in GH_PROXIES:
        url = (prefix + "/" + raw) if prefix else raw
        try:
            log(f"尝试下载 Tag 库: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "DrawCase"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            version = int(data.get("version", 0))
            tags = data.get("tags", [])
            if version <= taglib.current_version() or not tags:
                log(f"远端 Tag 库（v{version}）不比当前（v{taglib.current_version()}）新，已是最新。")
                return True
            with open(tags_remote_path(), "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False)
            log(f"Tag 库已更新到 v{version}（共 {len(tags)} 条，重启界面或点搜索刷新）")
            return True
        except Exception as e:
            log(f"该源不可用: {e}")
    log("Tag 库更新失败：所有 GitHub 源均不可访问，请检查网络。")
    return False


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


def _guess_qwen_base(name: str) -> str:
    tag = name.lower()
    return "Qwen/Qwen-Image-2.1" if "2.1" in tag else "Qwen/Qwen-Image"


def _load_gguf(gguf_path: str, dev: str, log: Callable[[str], None]) -> object:
    """GGUF：单独加载 transformer，再挂到对应版本官方基础管线（自动补齐文本编码器/VAE）."""
    import torch  # type: ignore
    from diffusers import (  # type: ignore
        GGUFQuantizationConfig,
        QwenImagePipeline,
        QwenImageTransformer2DModel,
    )

    base = _guess_qwen_base(os.path.basename(gguf_path))
    dtype = torch.bfloat16 if dev == "cuda" else torch.float32
    log(f"加载 GGUF transformer: {os.path.basename(gguf_path)}")
    log(f"基础组件仓库: {base}（文本编码器 / VAE，首次加载自动联网补齐）")
    transformer = QwenImageTransformer2DModel.from_single_file(
        gguf_path,
        quantization_config=GGUFQuantizationConfig(compute_dtype=dtype),
        torch_dtype=dtype,
    )
    return QwenImagePipeline.from_pretrained(base, transformer=transformer, torch_dtype=dtype)


class Generator:
    """对 diffusers 管线的轻封装：懒加载、线程内生成."""

    def __init__(self) -> None:
        self._pipe = None
        self._path: Optional[str] = None
        self._lora: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._pipe is not None

    @property
    def lora_path(self) -> Optional[str]:
        return self._lora

    def load_lora(self, lora_path: str, scale: float, log: Callable[[str], None]) -> bool:
        """向当前管线挂载 LoRA（SDXL / Qwen-Image 管线通用 best-effort）."""
        with self._lock:
            if self._pipe is None:
                log("模型未加载，请先加载主模型")
                return False
            try:
                try:
                    self._pipe.unload_lora_weights()  # 卸载旧 LoRA
                except Exception:
                    pass
                self._pipe.load_lora_weights(lora_path)
                try:
                    active = self._pipe.get_active_adapters()  # type: ignore[attr-defined]
                    if active:
                        self._pipe.set_adapters(active, adapter_weights=[scale] * len(active))
                except Exception:
                    # 部分管线不支持动态强度，回退为融合方式（强度固定）
                    self._pipe.fuse_lora(lora_scale=scale)  # type: ignore[attr-defined]
                    log("当前管线不支持动态强度，LoRA 已按固定强度融合")
                self._lora = lora_path
                log(f"LoRA 已挂载: {os.path.basename(lora_path)}（强度 {scale:.2f}）")
                return True
            except Exception as e:
                self._lora = None
                log(f"LoRA 挂载失败: {e}")
                return False

    def unload_lora(self, log: Callable[[str], None]) -> bool:
        with self._lock:
            if self._pipe is None:
                return False
            try:
                self._pipe.unload_lora_weights()
                self._lora = None
                log("LoRA 已卸载")
                return True
            except Exception as e:
                log(f"LoRA 卸载失败: {e}")
                return False

    def load(self, model_path: str, log: Callable[[str], None]) -> bool:
        """按本地路径加载模型（文件或目录）."""
        with self._lock:
            if self._pipe is not None and self._path == model_path:
                return True
            if self._pipe is not None:
                log("释放旧模型内存...")
                del self._pipe
                self._pipe = None
                self._path = None
            try:
                import torch  # type: ignore
                from diffusers import DiffusionPipeline  # type: ignore

                dev = torch_device()
                dtype = torch.float16 if dev == "cuda" else torch.float32
                log(f"加载模型: {model_path} (设备: {dev})")
                name = os.path.basename(model_path)

                if os.path.isfile(model_path):
                    if model_path.lower().endswith(".gguf"):
                        pipe = _load_gguf(model_path, dev, log)
                    else:
                        pipe = _load_single_file_pipe(model_path, dtype, log)
                elif os.path.isfile(os.path.join(model_path, "model_index.json")):
                    pipe = DiffusionPipeline.from_pretrained(model_path, torch_dtype=dtype)
                else:
                    w = _largest_weight(model_path)
                    if not w:
                        log("该目录内没有找到 .safetensors / .gguf 权重文件")
                        return False
                    if w.lower().endswith(".gguf"):
                        pipe = _load_gguf(w, dev, log)
                    else:
                        log(f"自动选择权重: {os.path.relpath(w, model_path)}")
                        pipe = _load_single_file_pipe(w, dtype, log)

                pipe.to(dev)
                if dev == "cuda":
                    pipe.enable_attention_slicing()
                self._pipe = pipe
                self._path = model_path
                self._lora = None  # 新管线需重新挂载 LoRA
                log("模型加载完成")
                low = name.lower()
                if "lightning" in low:
                    log("提示: Lightning 加速模型建议使用 步数=4、CFG=1.0")
                if "turbo" in low:
                    log("提示: Turbo 蒸馏模型建议使用 步数=8、CFG=1.0")
                if "v-pred" in low or "v_prediction" in low:
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
            self._path = None
            try:
                import torch  # type: ignore
                import gc  # type: ignore

                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
