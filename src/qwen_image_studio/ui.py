"""现代化轻量 UI（ttkbootstrap，如不可用则回退到纯 ttk 深色主题）.

布局：
- 左侧: 生成参数（提示词 + tag 库面板 / 负面提示 / 尺寸步数 CFG 种子）
- 右侧: 预览大图 + 状态日志
- 顶部: 模型选择 / 模型管理（下载）/ 依赖自检
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
    import ttkbootstrap as ttkb
    from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X, Y

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
    style.configure("Danger.TButton", background=PALETTE["err"], foreground="#ffffff")
    style.map("Danger.TButton", background=[("active", "#e05555")])
    style.configure("TEntry", fieldbackground=PALETTE["panel2"], foreground=PALETTE["fg"], insertcolor=PALETTE["fg"], borderwidth=0)
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
        self.downloader = engine.HFDownloader()
        self._busy = False
        self._preview_path: Optional[str] = None

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
        self.btn_deps = ttk.Button(right, text="依赖自检", command=self._on_check_deps)
        self.btn_deps.pack(side=LEFT, padx=4)
        ttk.Button(right, text="输出目录", command=self._open_outputs).pack(side=LEFT, padx=4)
        ttk.Button(right, text="关于", command=self._show_about).pack(side=LEFT, padx=4)

        # 模型行
        row = ttk.Frame(self, style="TFrame", padding=(14, 8, 14, 0))
        row.pack(fill=X)
        ttk.Label(row, text="模型", style="Sub.TLabel").pack(side=LEFT, padx=(0, 6))
        self.cmb_model = ttk.Combobox(row, state="readonly", width=42)
        self.cmb_model.pack(side=LEFT)
        self.cmb_model.bind("<<ComboboxSelected>>", lambda e: self._refresh_weights())
        ttk.Label(row, text="权重", style="Sub.TLabel").pack(side=LEFT, padx=(12, 6))
        self.cmb_weight = ttk.Combobox(row, state="readonly", width=34)
        self.cmb_weight.pack(side=LEFT)
        ttk.Button(row, text="模型管理…", command=self._open_models).pack(side=LEFT, padx=10)
        self.btn_load = ttk.Button(row, text="加载模型", style="Accent.TButton", command=self._on_load_model)
        self.btn_load.pack(side=LEFT)
        self.lbl_model_state = ttk.Label(row, text="未加载", style="Sub.TLabel")
        self.lbl_model_state.pack(side=LEFT, padx=10)

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

        # --- tag 库 ---
        tag_card = ttk.Labelframe(left, text=" 中文 Tag 库（点击插入 / 右键追加负面） ", style="Card.TLabelframe", padding=10)
        tag_card.pack(fill=BOTH, expand=True, pady=(10, 0))
        srow = ttk.Frame(tag_card, style="Panel.TFrame")
        srow.pack(fill=X)
        self.var_tagsearch = tk.StringVar()
        ent = ttk.Entry(srow, textvariable=self.var_tagsearch, width=30)
        ent.pack(side=LEFT, fill=X, expand=True)
        ent.bind("<KeyRelease>", lambda e: self._refresh_tags())
        ttk.Button(srow, text="搜索", width=6, command=self._refresh_tags).pack(side=LEFT, padx=(6, 0))

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
        log_card.pack(fill=BOTH, pady=(0, 0))
        self.txt_log = tk.Text(log_card, height=7, wrap="word", bg="#17181c", fg=PALETTE["sub"],
                               relief="flat", font=("Consolas", 9))
        self.txt_log.pack(fill=BOTH, expand=True)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(14, 6))
        bar.pack(fill=X, side="bottom")
        self.lbl_status = ttk.Label(bar, text="就绪", style="Panel.Sub.TLabel")
        self.lbl_status.pack(side=LEFT)
        ttk.Label(bar, text=f"{AUTHOR} <{AUTHOR_EMAIL}>  ·  {APP_NAME} v{VERSION}", style="Panel.Sub.TLabel").pack(side=RIGHT)

    # ------------------------------------------------------------ 逻辑
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
                    self.txt_log.insert(END, str(val) + "\n")
                    self.txt_log.see(END)
                elif kind == "status":
                    self.lbl_status.configure(text=str(val))
                elif kind == "progress":
                    self.progress.configure(value=float(val) * 100)
                elif kind == "preview":
                    self._show_preview(str(val))
                elif kind == "model_loaded":
                    ok = bool(val)
                    self.lbl_model_state.configure(text="已加载" if ok else "加载失败",
                                                   foreground=PALETTE["ok"] if ok else PALETTE["err"])
                    self.btn_load.configure(state="normal")
                elif kind == "deps_done":
                    self.btn_deps.configure(state="normal")
                elif kind == "busy":
                    self._busy = bool(val)
                    self.btn_gen.configure(state="disabled" if self._busy else "normal")
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _on_first_run(self) -> None:
        self._refresh_model_combo()
        self._log(f"{APP_NAME} v{VERSION}  作者: {AUTHOR} <{AUTHOR_EMAIL}>")
        self._log("提示: 首次使用请先「依赖自检」，再到「模型管理」下载模型。")
        threading.Thread(target=self._ensure_deps_bg, daemon=True).start()

    def _ensure_deps_bg(self) -> None:
        ok = engine.ensure_deps(self._log)
        self.q.put(("deps_done", ok))
        if ok:
            self._log("环境就绪 ✓")

    # ---------- 依赖 ----------
    def _on_check_deps(self) -> None:
        self.btn_deps.configure(state="disabled")
        threading.Thread(target=self._ensure_deps_bg, daemon=True).start()

    # ---------- 模型 ----------
    def _refresh_model_combo(self) -> None:
        local = engine.list_local_models()
        if local:
            self.cmb_model["values"] = local
            self.cmb_model.current(0)
            self._refresh_weights()
        else:
            self.cmb_model["values"] = []
            self._log("本地暂无模型，请打开「模型管理」下载。")

    def _refresh_weights(self) -> None:
        repo = self.cmb_model.get()
        files = engine.get_model_files(repo) if repo else []
        self.cmb_weight["values"] = ["（自动）"] + files
        self.cmb_weight.current(0)

    def _on_load_model(self) -> None:
        repo = self.cmb_model.get()
        if not repo:
            messagebox.showinfo(APP_NAME, "请先下载或选择模型。")
            return
        weight = None if self.cmb_weight.get() in ("（自动）", "") else self.cmb_weight.get()
        self.btn_load.configure(state="disabled")
        self.lbl_model_state.configure(text="加载中…", foreground=PALETTE["warn"])

        def work() -> None:
            ok = self.gen.load(repo, weight, self._log)
            self.q.put(("model_loaded", ok))

        threading.Thread(target=work, daemon=True).start()

    def _open_models(self) -> None:
        ModelsDialog(self)

    def _open_outputs(self) -> None:
        try:
            os.startfile(engine.outputs_dir())  # type: ignore[attr-defined]
        except Exception:
            self._log(f"输出目录: {engine.outputs_dir()}")

    # ---------- tag ----------
    def _refresh_tags(self) -> None:
        kw = self.var_tagsearch.get()
        cat = self.var_cat.get()
        items = taglib.search_tags(kw)
        if cat != "全部":
            items = [t for t in items if t[2] == cat]
        self.tree.delete(*self.tree.get_children())
        for zh, en, c in items:
            self.tree.insert("", END, values=(zh, en, c))

    def _insert_tag(self, en: str, target: Optional[tk.Text]) -> None:
        tgt = target or (self.txt_neg if self._focus_is_neg() else self.txt_prompt)
        cur = tgt.get("1.0", END).strip()
        sep = ", " if cur and not cur.endswith(",") else ("" if not cur else " ")
        tgt.insert(END, (sep if cur else "") + en + ("," if not cur.endswith(",") else ""))
        tgt.see(END)

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

    # ---------- 生成 ----------
    def _on_generate(self) -> None:
        if self.gen.loaded is False:
            messagebox.showinfo(APP_NAME, "请先加载模型。")
            return
        prompt = self.txt_prompt.get("1.0", END).strip()
        if not prompt:
            messagebox.showinfo(APP_NAME, "请输入提示词（可在 Tag 库双击插入）。")
            return
        neg = self.txt_neg.get("1.0", END).strip()
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
            "本地 Qwen-Image 生图工作台\n"
            "无需手动配置环境，从 HuggingFace 一键下载模型。\n"
            "内置中文 Tag 库，双击即可插入提示词。",
        )


# ------------------------------------------------------------------ 模型管理对话框
class ModelsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("模型管理")
        self.geometry("720x480")
        self.configure(bg=PALETTE["bg"])
        self.transient(master)
        self.grab_set()

        self.dl = engine.HFDownloader()
        self._downloading = False

        ttk.Label(self, text="推荐模型（HuggingFace）", style="Title.TLabel").pack(anchor="w", padx=14, pady=(14, 4))
        cols = ("name", "id", "size", "note")
        treef = ttk.Frame(self, style="TFrame")
        treef.pack(fill=BOTH, expand=True, padx=14)
        self.tree = ttk.Treeview(treef, columns=cols, show="headings")
        for cid, text, w in (("name", "名称", 200), ("id", "仓库 ID", 230), ("size", "体积", 130), ("note", "说明", 130)):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=w, anchor="w")
        vsb = ttk.Scrollbar(treef, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)
        for m in engine.BUILTIN_MODELS:
            self.tree.insert("", END, iid=m["id"], values=(m["name"], m["id"], m["size"], m["note"]))

        self.var_custom = tk.StringVar()
        crow = ttk.Frame(self, style="TFrame")
        crow.pack(fill=X, padx=14, pady=8)
        ttk.Label(crow, text="自定义仓库 ID:", style="Sub.TLabel").pack(side=LEFT)
        ttk.Entry(crow, textvariable=self.var_custom, width=34).pack(side=LEFT, padx=6)

        self.progress = ttk.Progressbar(self, maximum=100, value=0)
        self.progress.pack(fill=X, padx=14)
        self.lbl_dl = ttk.Label(self, text="", style="Sub.TLabel")
        self.lbl_dl.pack(anchor="w", padx=14)

        brow = ttk.Frame(self, style="TFrame")
        brow.pack(fill=X, padx=14, pady=(4, 14))
        self.btn_dl = ttk.Button(brow, text="下载选中模型", style="Accent.TButton", command=self._on_download)
        self.btn_dl.pack(side=LEFT)
        ttk.Button(brow, text="打开本地模型目录", command=self._open_dir).pack(side=LEFT, padx=8)
        ttk.Button(brow, text="刷新本地模型列表", command=self._refresh).pack(side=LEFT)
        ttk.Label(brow, text="已下载模型保存在用户数据目录，升级重装不丢失。", style="Sub.TLabel").pack(side=RIGHT)

        self._refresh()

    def _refresh(self) -> None:
        try:
            app = self.master  # 顶层 App
            if hasattr(app, "cmb_model"):
                local = engine.list_local_models()
                app.cmb_model["values"] = local  # type: ignore[attr-defined]
                if local:
                    app.cmb_model.current(0)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _open_dir(self) -> None:
        try:
            os.startfile(engine.models_dir())  # type: ignore[attr-defined]
        except Exception:
            self.lbl_dl.configure(text=f"模型目录: {engine.models_dir()}")

    def _on_download(self) -> None:
        repo = self.var_custom.get().strip() or (self.tree.selection()[0] if self.tree.selection() else "")
        if not repo or self._downloading:
            return
        self._downloading = True
        self.btn_dl.configure(state="disabled")
        self.lbl_dl.configure(text=f"开始下载: {repo} （支持断点续传，请保持网络畅通）")

        def log(m: str) -> None:
            self.lbl_dl.configure(text=m)

        def prog(p: float) -> None:
            self.progress.configure(value=p * 100)

        def work() -> None:
            ok = self.dl.download(repo, log, prog)
            self._downloading = False
            self.btn_dl.configure(state="normal")
            if ok:
                self.lbl_dl.configure(text=f"下载完成: {repo}")

        threading.Thread(target=work, daemon=True).start()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
