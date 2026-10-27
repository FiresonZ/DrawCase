"""内置中文 Tag 库（danbooru 风格常用标签 + 中文说明映射）.

结构: {中文名: 英文tag}, 分类展示, 支持搜索。
数据内置，首次启动无需联网；软件亦支持导入自定义 csv（中文名,英文tag,分类）。
"""

from __future__ import annotations

import csv
import json
import os
from typing import Dict, List, Tuple

# (中文名, 英文tag, 分类)
_RAW: List[Tuple[str, str, str]] = [
    # ---- 画质 ----
    ("杰作", "masterpiece", "画质"),
    ("最佳画质", "best quality", "画质"),
    ("超高清", "ultra high res", "画质"),
    ("高清", "high resolution", "画质"),
    ("细节丰富", "extremely detailed", "画质"),
    ("8K", "8k", "画质"),
    ("4K", "4k", "画质"),
    ("官方艺术", "official art", "画质"),
    ("绝美", "absurdres", "画质"),
    ("锋利对焦", "sharp focus", "画质"),
    ("电影级光影", "cinematic lighting", "画质"),
    ("体积光", "volumetric lighting", "画质"),
    ("伦勃朗光", "Rembrandt lighting", "画质"),
    ("逆光", "backlighting", "画质"),
    ("轮廓光", "rim light", "画质"),
    ("工作室灯光", "studio lighting", "画质"),
    # ---- 人物 ----
    ("一个女孩", "1girl", "人物"),
    ("两个女孩", "2girls", "人物"),
    ("一个男孩", "1boy", "人物"),
    ("独自一人", "solo", "人物"),
    ("少女", "young girl", "人物"),
    ("美女", "beautiful woman", "人物"),
    ("长发", "long hair", "人物"),
    ("短发", "short hair", "人物"),
    ("双马尾", "twintails", "人物"),
    ("马尾辫", "ponytail", "人物"),
    ("麻花辫", "braid", "人物"),
    ("白发", "white hair", "人物"),
    ("黑发", "black hair", "人物"),
    ("金发", "blonde hair", "人物"),
    ("银发", "silver hair", "人物"),
    ("红发", "red hair", "人物"),
    ("蓝发", "blue hair", "人物"),
    ("粉发", "pink hair", "人物"),
    ("紫发", "purple hair", "人物"),
    ("棕发", "brown hair", "人物"),
    ("绿发", "green hair", "人物"),
    ("长发及腰", "very long hair", "人物"),
    ("刘海", "bangs", "人物"),
    ("姬发式", "hime cut", "人物"),
    ("卷发", "curly hair", "人物"),
    ("直发", "straight hair", "人物"),
    ("猫耳", "cat ears", "人物"),
    ("狐耳", "fox ears", "人物"),
    ("兔耳", "rabbit ears", "人物"),
    ("精灵耳", "pointy ears", "人物"),
    ("兽耳", "animal ears", "人物"),
    ("异色瞳", "heterochromia", "人物"),
    ("红瞳", "red eyes", "人物"),
    ("蓝瞳", "blue eyes", "人物"),
    ("绿瞳", "green eyes", "人物"),
    ("金瞳", "golden eyes", "人物"),
    ("紫瞳", "purple eyes", "人物"),
    ("闭眼", "closed eyes", "人物"),
    ("笑容", "smile", "人物"),
    ("咧嘴笑", "grin", "人物"),
    ("脸红", "blush", "人物"),
    ("哭", "crying", "人物"),
    ("眼泪", "tears", "人物"),
    ("张嘴", "open mouth", "人物"),
    ("嘴闭合", "closed mouth", "人物"),
    ("吐舌头", "tongue out", "人物"),
    ("呆毛", "ahoge", "人物"),
    ("腮红", "blush stickers", "人物"),
    ("眼镜", "glasses", "人物"),
    ("太阳镜", "sunglasses", "人物"),
    ("痣", "mole", "人物"),
    ("泪痣", "mole under eye", "人物"),
    ("雀斑", "freckles", "人物"),
    ("黑白肤色", "dark skin", "人物"),
    ("苍白皮肤", "pale skin", "人物"),
    # ---- 服装 ----
    ("校服", "school uniform", "服装"),
    ("水手服", "sailor uniform", "服装"),
    ("JK制服", "japanese school uniform", "服装"),
    ("女仆装", "maid", "服装"),
    ("女仆头饰", "maid headdress", "服装"),
    ("和服", "kimono", "服装"),
    ("浴衣", "yukata", "服装"),
    ("旗袍", "china dress", "服装"),
    ("汉服", "hanfu", "服装"),
    ("洛丽塔", "lolita fashion", "服装"),
    ("哥特萝莉", "gothic lolita", "服装"),
    ("婚纱", "wedding dress", "服装"),
    ("白丝", "white thighhighs", "服装"),
    ("黑丝", "black thighhighs", "服装"),
    ("过膝袜", "thighhighs", "服装"),
    ("吊带袜", "zettai ryouiki", "服装"),
    ("连裤袜", "pantyhose", "服装"),
    ("泳装", "swimsuit", "服装"),
    ("比基尼", "bikini", "服装"),
    ("死库水", "school swimsuit", "服装"),
    ("连帽衫", "hoodie", "服装"),
    ("卫衣", "sweatshirt", "服装"),
    ("毛衣", "sweater", "服装"),
    ("衬衫", "shirt", "服装"),
    ("白衬衫", "white shirt", "服装"),
    ("短裙", "skirt", "服装"),
    ("百褶裙", "pleated skirt", "服装"),
    ("连衣裙", "dress", "服装"),
    ("公主裙", "princess dress", "服装"),
    ("西装", "suit", "服装"),
    ("领带", "necktie", "服装"),
    ("蝴蝶结", "hair bow", "服装"),
    ("发带", "hairband", "服装"),
    ("发夹", "hair ornament", "服装"),
    ("帽子", "hat", "服装"),
    ("贝雷帽", "beret", "服装"),
    ("巫女服", "miko", "服装"),
    ("修女服", "nun", "服装"),
    ("护士服", "nurse", "服装"),
    ("军装", "military uniform", "服装"),
    ("旗袍领", "china dress", "服装"),
    ("斗篷", "cape", "服装"),
    ("手套", "gloves", "服装"),
    ("围巾", "scarf", "服装"),
    ("外套", "coat", "服装"),
    ("风衣", "trench coat", "服装"),
    ("牛仔短裤", "denim shorts", "服装"),
    ("短裤", "shorts", "服装"),
    ("裤子", "pants", "服装"),
    ("高跟鞋", "high heels", "服装"),
    ("运动鞋", "sneakers", "服装"),
    ("靴子", "boots", "服装"),
    ("过膝靴", "thigh boots", "服装"),
    # ---- 姿势动作 ----
    ("站着", "standing", "动作"),
    ("坐着", "sitting", "动作"),
    ("蹲着", "squatting", "动作"),
    ("躺着", "lying", "动作"),
    ("趴着", "on stomach", "动作"),
    ("跪坐", "kneeling", "动作"),
    ("走路", "walking", "动作"),
    ("奔跑", "running", "动作"),
    ("跳跃", "jumping", "动作"),
    ("回头", "looking back", "动作"),
    ("看向观众", "looking at viewer", "动作"),
    ("仰视", "looking up", "动作"),
    ("双臂交叉", "arms crossed", "动作"),
    ("叉腰", "hands on hips", "动作"),
    ("双手背后", "arms behind back", "动作"),
    ("手放嘴边", "hand over own mouth", "动作"),
    ("比耶", "v sign", "动作"),
    ("挥手", "waving", "动作"),
    ("抱膝", "hugging own legs", "动作"),
    ("撑地坐", "arm support", "动作"),
    ("靠着", "leaning forward", "动作"),
    ("托腮", "hand on own cheek", "动作"),
    ("伸懒腰", "stretching", "动作"),
    ("舞蹈", "dancing", "动作"),
    ("睡觉", "sleeping", "动作"),
    ("举手", "raised arm", "动作"),
    ("捂脸", "covering face", "动作"),
    # ---- 构图 ----
    ("半身像", "upper body", "构图"),
    ("特写", "close-up", "构图"),
    ("面部特写", "face focus", "构图"),
    ("全身", "full body", "构图"),
    ("自上而下视角", "from above", "构图"),
    ("自下而上视角", "from below", "构图"),
    ("背面", "from behind", "构图"),
    ("侧面", "profile", "构图"),
    ("人物居中", "centered composition", "构图"),
    ("黄金比例构图", "golden ratio composition", "构图"),
    ("对称构图", "symmetrical composition", "构图"),
    ("广角", "wide shot", "构图"),
    ("鱼眼视角", "fisheye", "构图"),
    ("景深", "depth of field", "构图"),
    ("虚化背景", "blurry background", "构图"),
    ("前景虚化", "blurry foreground", "构图"),
    ("动态模糊", "motion blur", "构图"),
    ("大光圈", "bokeh", "构图"),
    ("广角镜头", "wide angle lens", "构图"),
    ("俯拍", "bird's-eye view", "构图"),
    # ---- 风格 ----
    ("动漫风格", "anime style", "风格"),
    ("厚涂", "impasto", "风格"),
    ("水彩", "watercolor", "风格"),
    ("水墨", "ink wash painting", "风格"),
    ("油画", "oil painting", "风格"),
    ("赛博朋克", "cyberpunk", "风格"),
    ("蒸汽朋克", "steampunk", "风格"),
    ("蒸汽波", "vaporwave", "风格"),
    ("极简主义", "minimalist", "风格"),
    ("写实风格", "photorealistic", "风格"),
    ("3D渲染", "3d render", "风格"),
    ("像素风", "pixel art", "风格"),
    ("扁平插画", "flat illustration", "风格"),
    ("厚涂风格", "thick painting", "风格"),
    ("幻想风", "fantasy style", "风格"),
    ("中国风", "chinese style", "风格"),
    ("日系", "japanese style", "风格"),
    ("欧式古风", "victorian style", "风格"),
    ("哥特风", "gothic", "风格"),
    ("洛可可", "rococo", "风格"),
    ("巴洛克", "baroque", "风格"),
    ("艺术线稿", "lineart", "风格"),
    ("素描", "sketch", "风格"),
    ("单色", "monochrome", "风格"),
    ("复古配色", "retro colors", "风格"),
    ("柔和色调", "pastel colors", "风格"),
    ("鲜艳配色", "vivid colors", "风格"),
    # ---- 场景 ----
    ("室内", "indoors", "场景"),
    ("室外", "outdoors", "场景"),
    ("教室", "classroom", "场景"),
    ("卧室", "bedroom", "场景"),
    ("厨房", "kitchen", "场景"),
    ("浴室", "bathroom", "场景"),
    ("图书馆", "library", "场景"),
    ("咖啡厅", "cafe", "场景"),
    ("便利店", "convenience store", "场景"),
    ("街道", "street", "场景"),
    ("城市夜景", "city night view", "场景"),
    ("霓虹灯", "neon lights", "场景"),
    ("雨夜", "rainy night", "场景"),
    ("雨天", "rain", "场景"),
    ("雪景", "snow", "场景"),
    ("樱花", "cherry blossoms", "场景"),
    ("花田", "flower field", "场景"),
    ("森林", "forest", "场景"),
    ("海边", "beach", "场景"),
    ("日落", "sunset", "场景"),
    ("日出", "sunrise", "场景"),
    ("星空", "starry sky", "场景"),
    ("银河", "milky way", "场景"),
    ("月亮", "moon", "场景"),
    ("太阳", "sun", "场景"),
    ("云海", "sea of clouds", "场景"),
    ("天空", "sky", "场景"),
    ("山", "mountain", "场景"),
    ("瀑布", "waterfall", "场景"),
    ("湖", "lake", "场景"),
    ("庭院", "garden", "场景"),
    ("神社", "shrine", "场景"),
    ("寺庙", "temple", "场景"),
    ("城堡", "castle", "场景"),
    ("废墟", "ruins", "场景"),
    ("太空", "outer space", "场景"),
    ("飞船内部", "spaceship interior", "场景"),
    ("赛博城市", "cyberpunk city", "场景"),
    # ---- 光效氛围 ----
    ("柔和光线", "soft lighting", "氛围"),
    ("强光", "hard lighting", "氛围"),
    ("暖色调", "warm lighting", "氛围"),
    ("冷色调", "cool lighting", "氛围"),
    ("朦胧感", "hazy", "氛围"),
    ("烟雾", "smoke", "氛围"),
    ("雾气", "fog", "氛围"),
    ("光芒", "light rays", "氛围"),
    ("丁达尔效应", "god rays", "氛围"),
    ("光斑", "light particles", "氛围"),
    ("萤火虫", "fireflies", "氛围"),
    ("蝴蝶", "butterflies", "氛围"),
    ("花瓣飘落", "falling petals", "氛围"),
    ("雪花飘落", "falling snow", "氛围"),
    ("雨滴", "rain drops", "氛围"),
    ("水面倒影", "water reflection", "氛围"),
    ("镜面反射", "mirror reflection", "氛围"),
    ("发光", "glowing", "氛围"),
    ("霓虹光晕", "neon glow", "氛围"),
    ("夜色", "night", "氛围"),
    ("黄昏", "dusk", "氛围"),
    ("清晨", "morning", "氛围"),
    # ---- 质量-负面 ----
    ("低质量", "low quality", "负面"),
    ("最差质量", "worst quality", "负面"),
    ("正常画质", "normal quality", "负面"),
    ("模糊", "blurry", "负面"),
    ("压缩痕迹", "jpeg artifacts", "负面"),
    ("水印", "watermark", "负面"),
    ("签名", "signature", "负面"),
    ("文字", "text", "负面"),
    ("错误手指", "bad hands", "负面"),
    ("多余手指", "extra fingers", "负面"),
    ("手指缺失", "missing fingers", "负面"),
    ("畸形四肢", "bad anatomy", "负面"),
    ("多余肢体", "extra limbs", "负面"),
    ("裁切", "cropped", "负面"),
    ("糟糕构图", "bad composition", "负面"),
    ("重影", "duplicate", "负面"),
    ("恐怖", "grotesque", "负面"),
]

CATEGORY_ORDER = ["画质", "人物", "服装", "动作", "构图", "风格", "场景", "氛围", "负面",
                  "通用", "角色", "作品", "画师", "元数据"]

BUILTIN_VERSION = 2  # 内置 Tag 库版本（data/tags.json 远程更新时递增）

_CACHE: List[Tuple[str, str, str]] = []
_LOADED_VER = BUILTIN_VERSION


def current_version() -> int:
    """当前生效的 Tag 库版本."""
    return max(BUILTIN_VERSION, _LOADED_VER)


def _packaged_tags() -> Optional[Tuple[int, List[Tuple[str, str, str]]]]:
    """加载随软件打包的全量 Tag 库（data/tags.json，约 10 万条）."""
    import sys

    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), "data", "tags.json"))
    # 开发模式：taglib.py 位于 src/qwen_image_studio/，仓库根在三级上层
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "data", "tags.json"))
    for p in candidates:
        try:
            if p and os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ver = int(data.get("version", 0))
                tags = [(str(z), str(e), str(c)) for z, e, c in data.get("tags", [])]
                if tags:
                    return ver, tags
        except Exception:
            continue
    return None


def _remote_tags() -> Optional[Tuple[int, List[Tuple[str, str, str]]]]:
    """加载远程更新的 Tag 库（appdata/tags_remote.json，由引擎经 GitHub 代理下载）."""
    try:
        from .version_info import appdata_dir

        p = os.path.join(appdata_dir(), "tags_remote.json")
        if not os.path.isfile(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        ver = int(data.get("version", 0))
        tags = [(str(z), str(e), str(c)) for z, e, c in data.get("tags", [])]
        if tags:
            return ver, tags
    except Exception:
        pass
    return None


def _appdata() -> str:
    from .version_info import appdata_dir

    d = appdata_dir()
    os.makedirs(d, exist_ok=True)
    return d


def load_tags() -> List[Tuple[str, str, str]]:
    """加载 Tag 库（版本最高者优先：远程更新 > 打包全量 > 内置精选），叠加用户 csv."""
    global _CACHE, _LOADED_VER
    if _CACHE:
        return _CACHE
    base = [(z, e, c) for z, e, c in _RAW]
    ver = BUILTIN_VERSION
    for src in (_packaged_tags(), _remote_tags()):
        if src and src[0] >= ver:
            ver, base = src
    _LOADED_VER = ver
    extra = os.path.join(_appdata(), "tags_extra.csv")
    try:
        if os.path.isfile(extra):
            with open(extra, "r", encoding="utf-8-sig") as f:
                for row in csv.reader(f):
                    if len(row) >= 2:
                        base.append((row[0].strip(), row[1].strip(), (row[2].strip() if len(row) > 2 else "自定义")))
    except Exception:
        pass
    _CACHE = base
    return base


def reload_tags() -> None:
    """外部更新 Tag 库后调用，清空缓存."""
    global _CACHE
    _CACHE = []


def search_tags(keyword: str) -> List[Tuple[str, str, str]]:
    """搜索：命中中文名、英文 tag 或分类。空关键词返回前 80 条."""
    kw = (keyword or "").strip().lower()
    tags = load_tags()
    if not kw:
        return tags[:80]
    res = []
    for zh, en, cat in tags:
        if kw in zh.lower() or kw in en.lower() or kw in cat.lower():
            res.append((zh, en, cat))
    return res[:200]


def categories() -> List[str]:
    seen = []
    for c in CATEGORY_ORDER:
        seen.append(c)
    for _, _, c in load_tags():
        if c not in seen:
            seen.append(c)
    return seen


def dump_builtin_json(path: str) -> None:
    """把内置 Tag 库导出为仓库 data/tags.json 格式（维护用）."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": BUILTIN_VERSION, "tags": [list(t) for t in _RAW]}, f, ensure_ascii=False, indent=1)
