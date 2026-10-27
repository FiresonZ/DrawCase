"""现代化轻量 UI（ttkbootstrap，如不可用则回退到纯 ttk 深色主题）.

布局：
- 顶部: 标题 / 依赖自检 / 输出目录 / 关于 + 本地模型选择行
- 左侧: 提示词与参数、中文 Tag 库、设置页（模型系列切换 / 本地模型选择 /
        模型文件夹管理 / 依赖状态进度 / HF 源）
- 右侧: 预览大图 + 进度 + 日志
- 底部状态栏: 作者信息 + 版本
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional

from . import engine, taglib
from .version_info import APP_NAME, APP_NAME_ZH, AUTHOR, AUTHOR_EMAIL, VERSION

try:
    import ttkbootstrap as ttkb  # noqa: F401

    HAS_TTB = True
except Exception:  # pragma: no cover
    HAS_TTB = False

PALETTE = {
    "bg": "#1e1f24",
    "panel": "#26272e",
    "panel2": "#2d2e37",
    "fg": "#e8e9ee",
    "sub": "#9aa0b0",
    "accent": "#7c6cf4",
    "accent2": "#4cc2ff",
    "ok": "#3ddc97",
    "warn": "#ffb454",
    "err": "#ff6b6b",
}


# ------------------------------------------------------------------ 主题辅助
def _dark_style(style: ttk.Style) -> None:
    style.theme_use("clam")
    style.configure(".", background=PALETTE["bg"], foreground=PALETTE["fg"], fieldbackground=PALETTE["panel2"])
    style.configure("TFrame", background=PALETTE["bg"])
    style.configure("Panel.TFrame", background=PALETTE["panel"])
    style.configure("TLabel", background=PALETTE["bg"], foreground=PALETTE["fg"])
    style.configure("Panel.TLabel", background=PALETTE["panel"], foreground=PALETTE["fg"])
    style.configure("Sub.TLabel", background=PALETTE["bg"], foreground=PALETTE["sub"])
    style.configure("Panel.Sub.TLabel", background=PALETTE["panel"], foreground=PALETTE["sub"])
    style.configure("Title.TLabel", background=PALETTE["bg"], foreground=PALETTE["accent2"], font=("Microsoft YaHei UI", 11, "bold"))
    style.configure("H1.TLabel", background=PALETTE["bg"], foreground=PALETTE["fg"], font=("Microsoft YaHei UI", 16, "bold"))
    style.configure("TButton", background=PALETTE["panel2"], foreground=PALETTE["fg"], borderwidth=0, focusthickness=0)
    style.map("TButton", background=[("active", PALETTE["accent"])])
    style.configure("Accent.TButton", background=PALETTE["accent"], foreground="#ffffff")
    style.map("Accent.TButton", background=[("active", "#6a5ae0"), ("disabled", "#555")])
    style.configure("TEntry", fieldbackground=PALETTE["panel2"], foreground=PALETTE["fg"], insertcolor=PALETTE["fg"], borderwidth=0)
    style.configure("TRadiobutton", background=PALETTE["bg"], foreground=PALETTE["fg"], focusthickness=0)
    style.map("TRadiobutton", background=[("active", PALETTE["bg"])])
    style.configure("TCheckbutton", background=PALETTE["bg"], foreground=PALETTE["fg"], focusthickness=0)
    style.configure("TCombobox", fieldbackground=PALETTE["panel2"], foreground=PALETTE["fg"], arrowcolor=PALETTE["fg"], borderwidth=0)
    style.map("TCombobox", fieldbackground=[("readonly", PALETTE["panel2"])])
    style.configure("Vertical.TScrollbar", background=PALETTE["panel2"], troughcolor=PALETTE["bg"], borderwidth=0)
    style.configure("Horizontal.TProgressbar", background=PALETTE["accent"], troughcolor=PALETTE["panel2"], borderwidth=0)
    style.configure("Card.TLabelframe", background=PALETTE["panel"], borderwidth=0)
    style.configure("Card.TLabelframe.Label", background=PALETTE["panel"], foreground=PALETTE["accent2"], font=("Microsoft YaHei UI", 9, "bold"))
    style.configure("TNotebook", background=PALETTE["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=PALETTE["panel"], foreground=PALETTE["sub"], padding=(14, 6))
    style.map("TNotebook.Tab", background=[("selected", PALETTE["accent"])], foreground=[("selected", "#ffffff")])


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME_ZH}  v{VERSION}")
        self.geometry("1280x820")
        self.minsize(1080, 700)
        self.configure(bg=PALETTE["bg"])

        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.gen = engine.Generator()
        self._busy = False
        self._preview_path: Optional[str] = None
        self._model_map: dict = {}

        style = ttk.Style(self)
        _dark_style(style)

        self._build_topbar()
        self._build_body()
        self._build_statusbar()
        self.after(80, self._poll_queue)
        self.after(200, self._on_first_run)

    # ------------------------------------------------------------ UI 构建
    def _build_topbar(self) -> None:
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 10))
        bar.pack(fill=X, side="top")
        ttk.Label(bar, text=f"✦ {APP_NAME_ZH}", style="H1.TLabel").pack(side=LEFT)
        ttk.Label(bar, text=f"  v{VERSION}  ·  作者 {AUTHOR}", style="Panel.Sub.TLabel").pack(side=LEFT, padx=(6, 0), pady=(8, 0))

        right = ttk.Frame(bar, style="Panel.TFrame")
        right.pack(side=RIGHT)
        ttk.Button(right, text="输出目录", command=self._open_outputs).pack(side=LEFT, padx=4)
        ttk.Button(right, text="关于", command=self._show_about).pack(side=LEFT, padx=4)

        # 模型行（本地扫描结果）
        row = ttk.Frame(self, style="TFrame", padding=(14, 8, 14, 0))
        row.pack(fill=X)
        ttk.Label(row, text="模型", style="Sub.TLabel").pack(side=LEFT, padx=(0, 6))
        self.cmb_model = ttk.Combobox(row, state="readonly", width=48)
        self.cmb_model.pack(side=LEFT)
        ttk.Button(row, text="刷新", width=5, command=self._refresh_model_combo).pack(side=LEFT, padx=(6, 0))
        ttk.Button(row, text="打开文件夹", command=self._open_model_root).pack(side=LEFT, padx=(6, 0))
        self.btn_load = ttk.Button(row, text="加载模型", style="Accent.TButton", command=self._on_load_model)
        self.btn_load.pack(side=LEFT, padx=(12, 0))
        self.lbl_model_state = ttk.Label(row, text="未加载", style="Sub.TLabel")
        self.lbl_model_state.pack(side=LEFT, padx=10)
        ttk.Label(row, text="（模型请放入安装目录 models 文件夹或设置里的自定义文件夹）",
                  style="Sub.TLabel").pack(side=LEFT, padx=(0, 10))

    def _build_body(self) -> None:
        body = ttk.Frame(self, style="TFrame")
        body.pack(fill=BOTH, expand=True, padx=14, pady=10)

        # ---------- 左列 ----------
        left = ttk.Frame(body, style="TFrame")
        left.pack(side=LEFT, fill=Y, padx=(0, 10))

        nb = ttk.Notebook(left)
        nb.pack(fill=X)

        # --- 提示词页 ---
        tab_pos = ttk.Frame(nb, style="TFrame", padding=6)
        nb.add(tab_pos, text="正向提示词")
        self.txt_prompt = tk.Text(tab_pos, height=6, wrap="word", bg=PALETTE["panel2"], fg=PALETTE["fg"],
                                  insertbackground=PALETTE["fg"], relief="flat", padx=8, pady=6,
                                  font=("Microsoft YaHei UI", 10))
        self.txt_prompt.pack(fill=X)

        # --- 负面页 ---
        tab_neg = ttk.Frame(nb, style="TFrame", padding=6)
        nb.add(tab_neg, text="负面提示词")
        self.txt_neg = tk.Text(tab_neg, height=6, wrap="word", bg=PALETTE["panel2"], fg=PALETTE["fg"],
                               insertbackground=PALETTE["fg"], relief="flat", padx=8, pady=6,
                               font=("Microsoft YaHei UI", 10))
        self.txt_neg.pack(fill=X)
        self.txt_neg.insert("1.0", "low quality, worst quality, blurry, watermark, text, bad hands")

        # --- 设置页 ---
        tab_set = ttk.Frame(nb, style="TFrame", padding=(6, 8))
        nb.add(tab_set, text="设置")

        # 模型系列
        frow = ttk.Frame(tab_set, style="TFrame")
        frow.pack(fill=X)
        ttk.Label(frow, text="模型系列:", style="Sub.TLabel").pack(side=LEFT)
        self.var_family = tk.StringVar(value=engine.FAMILY_LABELS.get(engine.get_family(), "Qwen-Image 系"))
        for fam, label in engine.FAMILY_LABELS.items():
            ttk.Radiobutton(frow, text=label, value=label, variable=self.var_family,
                            command=lambda f=fam: self._on_family_change(f)).pack(side=LEFT, padx=(10, 0))

        # 本地模型选择
        mrow = ttk.Frame(tab_set, style="TFrame")
        mrow.pack(fill=X, pady=(10, 0))
        ttk.Label(mrow, text="本地模型:", style="Sub.TLabel").pack(side=LEFT)
        self.cmb_set_model = ttk.Combobox(mrow, state="readonly", width=32)
        self.cmb_set_model.pack(side=LEFT, padx=(6, 6))
        ttk.Button(mrow, text="使用", style="Accent.TButton", width=6, command=self._on_use_model).pack(side=LEFT)

        # 模型文件夹管理
        dcard = ttk.Labelframe(tab_set, text=" 模型文件夹（升级重装不会覆盖其中的模型） ", style="Card.TLabelframe", padding=8)
        dcard.pack(fill=X, pady=(10, 0))
        self.lst_dirs = tk.Listbox(dcard, height=4, bg=PALETTE["panel2"], fg=PALETTE["fg"],
                                   relief="flat", selectbackground=PALETTE["accent"])
        self.lst_dirs.pack(fill=X)
        brow = ttk.Frame(dcard, style="Panel.TFrame")
        brow.pack(fill=X, pady=(6, 0))
        ttk.Button(brow, text="添加文件夹…", command=self._on_add_dir).pack(side=LEFT)
        ttk.Button(brow, text="移除选中", command=self._on_remove_dir).pack(side=LEFT, padx=6)
        ttk.Button(brow, text="打开内置模型目录", command=self._open_model_root).pack(side=LEFT)
        self.lbl_builtin = ttk.Label(dcard, text=f"内置: {engine.builtin_model_root('qwen')} 与 …\\SDXL",
                                     style="Panel.Sub.TLabel", wraplength=380, justify="left")
        self.lbl_builtin.pack(anchor="w", pady=(4, 0))

        # 依赖状态
        ecard = ttk.Labelframe(tab_set, text=" AI 运行依赖（首次使用自动安装，装在用户数据目录） ", style="Card.TLabelframe", padding=8)
        ecard.pack(fill=X, pady=(10, 0))
        self.lbl_deps = ttk.Label(ecard, text="检查中…", style="Panel.Sub.TLabel")
        self.lbl_deps.pack(anchor="w")
        self.deps_bar = ttk.Progressbar(ecard, maximum=100, value=0)
        self.deps_bar.pack(fill=X, pady=6)
        ttk.Button(ecard, text="检测 / 安装依赖", command=self._on_check_deps).pack(anchor="w")

        # HF 源
        hrow = ttk.Frame(tab_set, style="TFrame")
        hrow.pack(fill=X, pady=(10, 0))
        ttk.Label(hrow, text="HuggingFace 源:", style="Sub.TLabel").pack(side=LEFT)
        self.var_mirror = tk.StringVar(value="国内镜像" if engine.get_hf_endpoint() else "官方源")
        for text, val in (("官方源", "官方源"), ("国内镜像 hf-mirror.com", "国内镜像")):
            ttk.Radiobutton(hrow, text=text, value=val, variable=self.var_mirror,
                            command=self._apply_mirror).pack(side=LEFT, padx=(8, 0))
        ttk.Label(tab_set, text="镜像源用于 GGUF 模型首次加载时自动补齐官方基础组件（文本编码器/VAE）。",
                  style="Sub.TLabel", wraplength=380, justify="left").pack(anchor="w", pady=(6, 0))

        # --- tag 库 ---
        tag_card = ttk.Labelframe(left, text=" 中文 Tag 库（点击插入 / 右键追加负面） ", style="Card.TLabelframe", padding=10)
        tag_card.pack(fill=BOTH, expand=True, pady=(10, 0))
        srow = ttk.Frame(tag_card, style="Panel.TFrame")
        srow.pack(fill=X)
        self.var_tagsearch = tk.StringVar()
        ent = ttk.Entry(srow, textvariable=self.var_tagsearch, width=24)
        ent.pack(side=LEFT, fill=X, expand=True)
        ent.bind("<KeyRelease>", lambda e: self._refresh_tags())
        ttk.Button(srow, text="搜索", width=5, command=self._refresh_tags).pack(side=LEFT, padx=(6, 0))
        self.btn_tagupd = ttk.Button(srow, text="更新 Tag 库", command=self._on_update_tags)
        self.btn_tagupd.pack(side=LEFT, padx=(6, 0))

        # 分类过滤
        crow = ttk.Frame(tag_card, style="Panel.TFrame")
        crow.pack(fill=X, pady=(6, 2))
        self.var_cat = tk.StringVar(value="全部")
        self.cmb_cat = ttk.Combobox(crow, textvariable=self.var_cat, state="readonly", width=12,
                                    values=["全部"] + taglib.categories())
        self.cmb_cat.pack(side=LEFT)
        self.cmb_cat.bind("<<ComboboxSelected>>", lambda e: self._refresh_tags())
        ttk.Label(crow, text="双击标签插入到当前焦点输入框", style="Panel.Sub.TLabel").pack(side=LEFT, padx=8)

        treef = ttk.Frame(tag_card, style="Panel.TFrame")
        treef.pack(fill=BOTH, expand=True, pady=(4, 0))
        cols = ("zh", "en", "cat")
        self.tree = ttk.Treeview(treef, columns=cols, show="headings", height=12)
        for cid, text, w in (("zh", "中文", 140), ("en", "英文 Tag", 220), ("cat", "分类", 70)):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=w, anchor="w")
        vsb = ttk.Scrollbar(treef, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)
        self.tree.bind("<Double-1>", self._on_tag_double)
        self.tree.bind("<Return>", self._on_tag_double)
        self.tree.bind("<Button-3>", self._on_tag_right)
        self._refresh_tags()

        # --- 参数 ---
        prow = ttk.Frame(left, style="TFrame")
        prow.pack(fill=X, pady=(10, 0))

        def _spin(parent, label, frm, to, init):
            f = ttk.Frame(parent, style="TFrame")
            f.pack(side=LEFT, padx=(0, 12))
            ttk.Label(f, text=label, style="Sub.TLabel").pack(anchor="w")
            var = tk.IntVar(value=init)
            sp = ttk.Spinbox(f, from_=frm, to=to, textvariable=var, width=7)
            sp.pack()
            return var

        self.var_w = _spin(prow, "宽度", 256, 4096, 1024)
        self.var_h = _spin(prow, "高度", 256, 4096, 1024)
        self.var_steps = _spin(prow, "步数", 1, 100, 20)
        self.var_seed = _spin(prow, "种子", 0, 2**31 - 1, 42)

        crow2 = ttk.Frame(left, style="TFrame")
        crow2.pack(fill=X, pady=(8, 0))
        ttk.Label(crow2, text="CFG", style="Sub.TLabel").pack(side=LEFT, padx=(0, 6))
        self.var_cfg = tk.DoubleVar(value=4.0)
        ttk.Scale(crow2, from_=1.0, to=15.0, variable=self.var_cfg, length=140).pack(side=LEFT)
        self.lbl_cfg = ttk.Label(crow2, text="4.0", style="Sub.TLabel")
        self.lbl_cfg.pack(side=LEFT, padx=6)
        self.var_cfg.trace_add("write", lambda *a: self.lbl_cfg.configure(text=f"{self.var_cfg.get():.1f}"))

        self.btn_gen = ttk.Button(left, text="▶ 开始生成", style="Accent.TButton", command=self._on_generate)
        self.btn_gen.pack(fill=X, pady=(12, 0), ipady=6)

        # ---------- 右列 ----------
        right = ttk.Frame(body, style="TFrame")
        right.pack(side=LEFT, fill=BOTH, expand=True)

        prev_card = ttk.Labelframe(right, text=" 预览 ", style="Card.TLabelframe", padding=10)
        prev_card.pack(fill=BOTH, expand=True)
        self.lbl_preview = tk.Label(prev_card, bg="#17181c", fg=PALETTE["sub"],
                                    text="生成结果将在此显示", font=("Microsoft YaHei UI", 11))
        self.lbl_preview.pack(fill=BOTH, expand=True)
        self._preview_img = None  # type: ignore[var-annotated]

        prow2 = ttk.Frame(prev_card, style="Panel.TFrame")
        prow2.pack(fill=X, pady=(8, 0))
        ttk.Button(prow2, text="保存为…", command=self._save_preview).pack(side=LEFT)
        ttk.Button(prow2, text="打开输出目录", command=self._open_outputs).pack(side=LEFT, padx=8)
        ttk.Button(prow2, text="复制图片", command=self._copy_preview).pack(side=LEFT)
        self.var_prev_info = tk.StringVar(value="")
        ttk.Label(prow2, textvariable=self.var_prev_info, style="Panel.Sub.TLabel").pack(side=RIGHT)

        self.progress = ttk.Progressbar(right, maximum=100, value=0)
        self.progress.pack(fill=X, pady=(10, 4))

        log_card = ttk.Labelframe(right, text=" 日志 ", style="Card.TLabelframe", padding=6)
        log_card.pack(fill=BOTH)
        self.txt_log = tk.Text(log_card, height=7, wrap="word", bg="#17181c", fg=PALETTE["sub"],
                               relief="flat", font=("Consolas", 9))
        self.txt_log.pack(fill=BOTH, expand=True)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 6))
        bar.pack(fill=X, side="bottom")
        self.lbl_status = ttk.Label(bar, text="就绪", style="Panel.Sub.TLabel")
        self.lbl_status.pack(side=LEFT)
        ttk.Label(bar, text=f"{AUTHOR} <{AUTHOR_EMAIL}>  ·  {APP_NAME} v{VERSION}", style="Panel.Sub.TLabel").pack(side=RIGHT)

    # ------------------------------------------------------------ 队列
    def _log(self, msg: str) -> None:
        self.q.put(("log", msg))

    def _status(self, msg: str) -> None:
        self.q.put(("status", msg))

    def _progress(self, p: float) -> None:
        self.q.put(("progress", p))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.txt_log.insert("end", str(val) + "\n")
                    self.txt_log.see("end")
                elif kind == "status":
                    self.lbl_status.configure(text=str(val))
                elif kind == "progress":
                    self.progress.configure(value=float(val) * 100)
                elif kind == "preview":
                    self._show_preview(str(val))
                elif kind == "deps":
                    name, frac = val
                    self.lbl_deps.configure(text=f"正在安装 {name} … {int(frac * 100)}%")
                    self.deps_bar.configure(value=float(frac) * 100)
                elif kind == "deps_status":
                    self._update_deps_status(dict(val))
                elif kind == "tags_updated":
                    self._refresh_tags()
                    self.cmb_cat["values"] = ["全部"] + taglib.categories()
                    self.btn_tagupd.configure(state="normal")
                    self._log("Tag 库列表已刷新")
                elif kind == "model_loaded":
                    ok = bool(val)
                    self.lbl_model_state.configure(text="已加载" if ok else "加载失败",
                                                   foreground=PALETTE["ok"] if ok else PALETTE["err"])
                    self.btn_load.configure(state="normal")
                elif kind == "busy":
                    self._busy = bool(val)
                    self.btn_gen.configure(state="disabled" if self._busy else "normal")
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    # ------------------------------------------------------------ 初始化
    def _on_first_run(self) -> None:
        engine.apply_saved_endpoint()  # 在任何 huggingface_hub 导入前恢复镜像设置
        self._refresh_model_combo()
        self._refresh_set_model_combo()
        self._refresh_dirs()
        self._log(f"{APP_NAME} v{VERSION}  作者: {AUTHOR} <{AUTHOR_EMAIL}>")
        self._log("首次使用：软件正在自动安装 AI 依赖（详见「设置」页进度），"
                  "然后把下载好的模型放入安装目录 models 文件夹。")
        threading.Thread(target=self._ensure_deps_bg, daemon=True).start()

    # ------------------------------------------------------------ 依赖
    def _update_deps_status(self, st: dict) -> None:
        if st.get("libs") and st.get("torch"):
            self.lbl_deps.configure(text="已安装 ✓（全部 AI 运行依赖就绪）", foreground=PALETTE["ok"])
            self.deps_bar.configure(value=100)
        else:
            miss = []
            if not st.get("libs"):
                miss.append("依赖库（diffusers 等）")
            if not st.get("torch"):
                miss.append("PyTorch")
            self.lbl_deps.configure(text="未安装: " + "、".join(miss), foreground=PALETTE["warn"])

    def _on_check_deps(self) -> None:
        threading.Thread(target=self._ensure_deps_bg, daemon=True).start()

    def _ensure_deps_bg(self) -> None:
        self.q.put(("deps_status", engine.deps_status()))
        ok = engine.ensure_deps(
            log=self._log,
            progress=lambda name, frac: self.q.put(("deps", (name, frac))),
        )
        self.q.put(("deps_status", engine.deps_status()))
        if ok:
            self._log("环境就绪 ✓")

    # ------------------------------------------------------------ 模型
    def _refresh_model_combo(self) -> None:
        """刷新主界面模型下拉（按当前系列扫描本地文件夹）."""
        fam = engine.get_family()
        models = engine.scan_models(fam)
        self._model_map = {m["name"]: m for m in models}
        names = list(self._model_map.keys())
        self.cmb_model["values"] = names
        self.cmb_set_model["values"] = names
        active = engine.get_active_model()
        if active and active["name"] in self._model_map:
            self.cmb_model.set(active["name"])
            self.cmb_set_model.set(active["name"])
        elif names:
            self.cmb_model.current(0)
            self.cmb_set_model.set(names[0])
        else:
            self.cmb_model.set("")
            self.cmb_set_model.set("")
        if not names:
            self._log(f"「{engine.FAMILY_LABELS.get(fam)}」暂无本地模型，请把模型放入: {engine.builtin_model_root(fam)}")

    def _refresh_set_model_combo(self) -> None:
        pass  # 与主界面下拉同步刷新（_refresh_model_combo 已同时更新）

    def _on_family_change(self, family: str) -> None:
        engine.set_family(family)
        self._log(f"已切换模型系列: {engine.FAMILY_LABELS.get(family)}")
        self._refresh_model_combo()
        self.lbl_builtin.configure(
            text=f"内置: {engine.builtin_model_root('qwen')} 与 {engine.builtin_model_root('sdxl')}")

    def _on_use_model(self) -> None:
        name = self.cmb_set_model.get()
        if not name:
            messagebox.showinfo(APP_NAME, "没有可选模型，请先在模型文件夹中放入模型后点「刷新」。")
            return
        entry = self._model_map.get(name)
        if entry:
            engine.set_active_model(entry)
            self.cmb_model.set(name)
            self._log(f"已选择使用模型: {name}")

    def _on_load_model(self) -> None:
        name = self.cmb_model.get()
        entry = self._model_map.get(name) or engine.get_active_model()
        if not entry:
            messagebox.showinfo(APP_NAME, "请先在模型文件夹中放入模型，并在「设置」页选择。")
            return
        path = entry["path"]
        self.btn_load.configure(state="disabled")
        self.lbl_model_state.configure(text="加载中…", foreground=PALETTE["warn"])

        def work() -> None:
            ok = self.gen.load(path, self._log)
            self.q.put(("model_loaded", ok))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 模型文件夹
    def _refresh_dirs(self) -> None:
        self.lst_dirs.delete(0, "end")
        for d in engine.custom_model_dirs():
            self.lst_dirs.insert("end", d)
        self.lbl_builtin.configure(
            text=f"内置: {engine.builtin_model_root('qwen')} 与 {engine.builtin_model_root('sdxl')}")

    def _on_add_dir(self) -> None:
        d = filedialog.askdirectory(title="选择模型文件夹")
        if d:
            engine.add_model_dir(os.path.normpath(d))
            self._refresh_dirs()
            self._refresh_model_combo()
            self._log(f"已添加模型文件夹: {d}")

    def _on_remove_dir(self) -> None:
        sel = self.lst_dirs.curselection()
        if sel:
            d = self.lst_dirs.get(sel[0])
            engine.remove_model_dir(d)
            self._refresh_dirs()
            self._refresh_model_combo()
            self._log(f"已移除模型文件夹: {d}")

    def _open_model_root(self) -> None:
        d = engine.builtin_model_root(engine.get_family())
        try:
            os.startfile(d)  # type: ignore[attr-defined]
        except Exception:
            self._log(f"模型目录: {d}")

    def _open_outputs(self) -> None:
        try:
            os.startfile(engine.outputs_dir())  # type: ignore[attr-defined]
        except Exception:
            self._log(f"输出目录: {engine.outputs_dir()}")

    # ------------------------------------------------------------ HF 源
    def _apply_mirror(self) -> None:
        val = self.var_mirror.get()
        engine.set_hf_endpoint(engine.HF_MIRROR if val == "国内镜像" else engine.HF_OFFICIAL)
        self._log(f"已切换 HuggingFace 源: {'hf-mirror.com（国内镜像）' if val == '国内镜像' else '官方 huggingface.co'}")

    # ------------------------------------------------------------ tag
    def _on_update_tags(self) -> None:
        self.btn_tagupd.configure(state="disabled")
        self._log("开始更新 Tag 库（自动尝试 GitHub 直连与代理源）…")

        def work() -> None:
            ok = engine.update_tags_from_github(self._log)
            if ok:
                taglib.reload_tags()
                self.q.put(("tags_updated", True))

        threading.Thread(target=work, daemon=True).start()

    def _refresh_tags(self) -> None:
        kw = self.var_tagsearch.get()
        cat = self.var_cat.get()
        items = taglib.search_tags(kw)
        if cat != "全部":
            items = [t for t in items if t[2] == cat]
        self.tree.delete(*self.tree.get_children())
        for zh, en, c in items:
            self.tree.insert("", "end", values=(zh, en, c))

    def _insert_tag(self, en: str, target: Optional[tk.Text]) -> None:
        tgt = target or (self.txt_neg if self._focus_is_neg() else self.txt_prompt)
        cur = tgt.get("1.0", "end").strip()
        tgt.insert("end", (", " if cur and not cur.endswith(",") else "") + en + ",")
        tgt.see("end")

    def _focus_is_neg(self) -> bool:
        w = self.focus_get()
        return w in (self.txt_neg,)

    def _on_tag_double(self, _e: object) -> None:
        sel = self.tree.selection()
        if sel:
            en = self.tree.item(sel[0], "values")[1]
            self._insert_tag(en, None)

    def _on_tag_right(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            en = self.tree.item(iid, "values")[1]
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="插入到正面提示词", command=lambda: self._insert_tag(en, self.txt_prompt))
            menu.add_command(label="插入到负面提示词", command=lambda: self._insert_tag(en, self.txt_neg))
            menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------ 生成
    def _on_generate(self) -> None:
        if not self.gen.loaded:
            messagebox.showinfo(APP_NAME, "请先加载模型（模型放入 models 文件夹后在下拉框选择）。")
            return
        prompt = self.txt_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showinfo(APP_NAME, "请输入提示词（可在 Tag 库双击插入）。")
            return
        neg = self.txt_neg.get("1.0", "end").strip()
        seed = int(self.var_seed.get())
        self.q.put(("busy", True))
        self._status("生成中…")

        def work() -> None:
            path = self.gen.generate(
                prompt=prompt,
                negative_prompt=neg,
                width=int(self.var_w.get()) // 8 * 8,
                height=int(self.var_h.get()) // 8 * 8,
                steps=int(self.var_steps.get()),
                guidance=float(self.var_cfg.get()),
                seed=seed,
                log=self._log,
                progress=self._progress,
            )
            self.q.put(("busy", False))
            if path:
                self.q.put(("preview", path))
                self._status("完成 ✓")

        threading.Thread(target=work, daemon=True).start()

    def _show_preview(self, path: str) -> None:
        try:
            from PIL import Image, ImageTk  # type: ignore
        except Exception:
            self._log(f"[预览] 已生成: {path}（安装 pillow 后可显示预览）")
            return
        try:
            img = Image.open(path)
            self.var_prev_info.set(f"{os.path.basename(path)}  {img.width}x{img.height}")
            w = max(self.lbl_preview.winfo_width(), 10)
            h = max(self.lbl_preview.winfo_height(), 10)
            scale = min(w / img.width, h / img.height)
            img2 = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
            self._preview_img = ImageTk.PhotoImage(img2)
            self.lbl_preview.configure(image=self._preview_img, text="")
            self._preview_path = path
        except Exception as e:
            self._log(f"预览失败: {e}")

    def _save_preview(self) -> None:
        if not self._preview_path:
            return
        dst = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if dst:
            import shutil

            shutil.copyfile(self._preview_path, dst)
            self._log(f"已保存到 {dst}")

    def _copy_preview(self) -> None:
        if not self._preview_path:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(self._preview_path)
            self._log("已复制图片路径到剪贴板")
        except Exception:
            pass

    def _show_about(self) -> None:
        messagebox.showinfo(
            f"关于 {APP_NAME}",
            f"{APP_NAME} · {APP_NAME_ZH}\n"
            f"版本: {VERSION}\n\n"
            f"作者: {AUTHOR}\n邮箱: {AUTHOR_EMAIL}\n\n"
            "本地生图工作台（Qwen-Image 系 / SDXL 系）\n"
            "模型请自行从 HuggingFace 下载后放入模型文件夹。\n"
            "内置中文 Tag 库，双击即可插入提示词。",
        )


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
