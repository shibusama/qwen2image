"""千问 API 封装：qwen-plus 摘要 + qwen-image-3.0 生图。

API 地址统一从 .env 的 DASHSCOPE_BASE_URL 读取（海外千问平台
https://dashscope-intl.aliyuncs.com/api/v1；阿里云百炼大陆站
https://dashscope.aliyuncs.com/api/v1），未配置时回退到 DEFAULT_BASE_URL。
Qwen-Image 不支持 OpenAI compatible-mode，必须走 DashScope 原生接口。
"""

import base64
import json
import os
import re

import dashscope
from dashscope import Generation, MultiModalConversation

# 兜底 API 地址（千问平台）；大陆阿里云百炼原生端点
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

# 写死到代码的 API Key（如需更换在此修改）
DASHSCOPE_API_KEY = "sk-a78bce9c2353443681ba0704d958ce99"

# 摘要模型（写死）
SUMMARY_MODEL = "qwen-plus"
# 生图模型（写死；qwen-image-3.0 已额度耗尽，不再使用，从 3.0-pro 起）
IMAGE_MODEL = "qwen-image-3.0-pro"

# 可用的文生图模型候选池（额度用完自动轮换）。按质量/偏好从优到次排列。
# 注意：qwen-image-3.0 额度已耗尽，故不包括在内。
IMAGE_MODEL_CANDIDATES = [
    "qwen-image-3.0-pro",
    "qwen-image-max",
    "qwen-image-max-2025-12-30",
    "qwen-image-2.0-pro",
    "qwen-image-2.0-pro-2026-06-22",
    "qwen-image-2.0",
    "qwen-image-plus-2026-01-09",
    "wan2.7-image",
    "z-image-turbo",
]

# 进程内已判定“额度耗尽”的生图模型，不再重试
_EXHAUSTED_MODELS: set[str] = set()


def _configure_base_url():
    """配置 DashScope 端点：优先取 .env 的 DASHSCOPE_BASE_URL，否则用写死的大陆端点。"""
    url = (os.getenv("DASHSCOPE_BASE_URL") or "").strip().rstrip("/")
    dashscope.base_http_api_url = url or DEFAULT_BASE_URL


_configure_base_url()


class QwenError(Exception):
    pass


def _resolve_key(api_key):
    """优先用请求传入的 Key；否则用代码中写死的 DASHSCOPE_API_KEY。"""
    return (api_key or "").strip() or DASHSCOPE_API_KEY


def summarize(source_text: str, api_key: str = None, kind: str = "poster", model: str = None) -> dict:
    """用文本模型把原文提炼成结构化 JSON（poster=信息图，mindmap=思维导图）。

    model 缺省时用 SUMMARY_MODEL；实际生成默认使用写死的摘要模型。
    """
    from prompt_builder import build_summary_mindmap_prompt, build_summary_prompt

    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key")
    prompt = (
        build_summary_mindmap_prompt(source_text)
        if kind == "mindmap"
        else build_summary_prompt(source_text)
    )
    resp = Generation.call(
        api_key=key,
        model=model or SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        result_format="message",
    )
    if resp.status_code == 200:
        text = resp.output.choices[0].message.content
    else:
        # 推理模型（如 qwq 系列）只支持流式模式 → 自动用流式重试
        msg = str(getattr(resp, "message", resp))
        if "stream" not in msg.lower():
            raise QwenError(f"摘要失败 ({resp.status_code})：{msg}")
        parts = []
        for chunk in Generation.call(
            api_key=key,
            model=model or SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            result_format="message",
            stream=True,
        ):
            if chunk.status_code != 200:
                raise QwenError(f"摘要失败 ({chunk.status_code})：{getattr(chunk, 'message', chunk)}")
            content = chunk.output.choices[0].message.content
            if content:
                parts.append(content)
        text = "".join(parts)
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise QwenError("摘要模型未返回有效 JSON")
    data = json.loads(m.group(0))
    if not isinstance(data.get("points"), list):
        data["points"] = []
    return data


def generate_poster(poster_prompt: str, size: str = "2048*2048", api_key: str = None, model: str = None) -> str:
    """同步生图，返回图片 URL。model 缺省时用 IMAGE_MODEL（.env 可覆盖）。"""
    from prompt_builder import NEGATIVE_PROMPT

    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key")
    model = model or IMAGE_MODEL
    # 图像编辑模型（*edit*）不能做纯文生图，提前给出明确提示
    if "edit" in model.lower():
        raise QwenError(
            f"模型 {model} 是图像编辑模型（需输入图片），不能直接文生图。"
            "请改用文生图模型，如 qwen-image-3.0 / qwen-image-max"
        )
    resp = MultiModalConversation.call(
        api_key=key,
        model=model,
        messages=[{"role": "user", "content": [{"text": poster_prompt}]}],
        result_format="message",
        stream=False,
        watermark=False,
        prompt_extend=True,
        negative_prompt=NEGATIVE_PROMPT,
        size=size,
    )
    if resp.status_code != 200:
        raise QwenError(f"生图失败 ({resp.status_code})：{getattr(resp, 'message', resp)}")
    content = resp.output.choices[0].message.content
    for item in content:
        if isinstance(item, dict) and item.get("image"):
            return item["image"]
    raise QwenError("生图结果中未找到图片 URL")


def _is_quota_error(err: QwenError) -> bool:
    """判断错误信息是否属于“额度/余额不足”，是则返回 True（触发换模型）。"""
    msg = str(err).lower()
    return any(
        kw in msg
        for kw in (
            "free quota exhausted",   # 免费额度耗尽（千问403）
            "insufficient balance",   # 余额不足
            "quota",                  # 通用额度
            "balance",
            "exceeded",               # 用量超限
            "额度",                   # 中文提示
            "余额",
            "出账失败",
            "cash",                   # 需充值
            "add funds",
        )
    )


def _build_order(preferred: str, base: list[str], forbid_edit: bool = False) -> list[str]:
    """构建模型尝试顺序：preferred 若有效则置顶，其余按 base 顺序；可选排除 edit 模型。"""
    pref = (preferred or "").strip()
    order: list[str] = []
    if pref and (not forbid_edit or "edit" not in pref.lower()):
        order.append(pref)
    for m in base:
        if m not in order and (not forbid_edit or "edit" not in m.lower()):
            order.append(m)
    return order


def _rotate_with_fallback(
    order: list[str], exhausted: set[str], call_one, all_exhausted_prefix: str
) -> tuple[object, str, str | None]:
    """通用额度轮换：按 order 逐个调用 call_one(model)；额度不足标记耗尽换下一个。

    返回 (result, used_model, note)；全部耗尽抛 QwenError。
    """
    quota_failures = []
    used: str | None = None
    result = None
    for model in order:
        if model in exhausted:
            continue
        try:
            result = call_one(model)
            used = model
            break
        except QwenError as e:
            if _is_quota_error(e):
                exhausted.add(model)          # 标记此模型额度已耗尽
                quota_failures.append(f"{model} 额度用尽")
                continue                       # 换下一个模型重试
            raise                              # 非额度类错误：如实抛出
    if used is None:
        raise QwenError(
            all_exhausted_prefix + "；".join(quota_failures)
            + "。请在千问控制台充值 / 关闭“仅免费额度”。"
        )
    note = None
    if quota_failures:
        note = "；".join(quota_failures) + f"，已自动改用 {used}"
    return result, used, note


def generate_poster_with_fallback(
    poster_prompt: str, size: str = "2048*2048", api_key: str = None, preferred_model: str = None
) -> tuple[str, str, str | None]:
    """文生图轮换：优先用户选定模型，额度用完自动换下一个；返回 (image_url, used_model, note)。"""
    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key")
    order = _build_order(preferred_model, [IMAGE_MODEL, *IMAGE_MODEL_CANDIDATES], forbid_edit=True)
    url, used, note = _rotate_with_fallback(
        order,
        _EXHAUSTED_MODELS,
        lambda m: generate_poster(poster_prompt, size=size, api_key=api_key, model=m),
        "所有候选生图模型的额度均已耗尽：",
    )
    return url, used, note


def image_to_base64(image_url: str) -> str:
    """下载图片并转为 base64 data URL，避免前端跨域/防盗链问题。"""
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    }
    resp = requests.get(image_url, headers=headers, timeout=60)
    resp.raise_for_status()
    mime = resp.headers.get("Content-Type", "image/png").split(";")[0]
    b64 = base64.b64encode(resp.content).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ============ 图生图（图像编辑）============

# 风格 → 编辑指令（写死在后台；用户在前端只选风格按钮）
IMG2IMG_STYLES = {
    "美式波普风": (
        "将图片转为矢量平面插画：大半调网点质感，波普艺术风格插画，粗黑轮廓线，"
        "剔除多余细节，平涂大色块，无渐变，高对比度，班戴点半色调网点印刷纹理，"
        "美式复古漫画质感，波普艺术标志性的高饱和撞色风格（蓝、粉、黄），怀旧做旧效果，"
        "通过半调网点疏密表达光影，高饱和色彩鲜明大胆，整体色调统一，丝网印刷质感，"
        "扁平化构图，干净利落，矢量插画风格，8K 高清细节。保持原图主体内容与构图。"
    ),
    "水彩插画": (
        "以清新水彩插画风格重绘这张图：柔和晕染、通透淡彩、纸张纹理、"
        "边缘自然渗化。保持主体内容与构图。"
    ),
    "油画": (
        "以古典油画风格重绘这张图：厚重笔触、浓郁色彩、光影层次丰富、"
        "画布质感。保持主体内容与构图。"
    ),
    "赛博朋克": (
        "以赛博朋克风格重绘这张图：霓虹紫蓝橙配色、夜雨街景、全息光影、"
        "未来科技感。保持主体内容与构图。"
    ),
    "像素风": (
        "将图片转为像素风格图：画面由 8-bit 极大的像素块组成，复古游戏画风，"
        "剔除原图细节，剔除原图色彩，整体使用高明度高饱和度马卡龙（青粉）渐变配色，"
        "轮廓干净硬朗，保留原图构图和主体，通过像素块大小来表达光影，简化背景，"
        "无多余杂色，无文字，无水印，画面干净统一。保持原图主体内容与构图。"
    ),
    "素描线稿": (
        "以素描线稿风格重绘这张图：黑白铅笔线条、明暗排线、干净背景。"
        "保持主体内容与构图。"
    ),
    "国潮插画": (
        "将图片转为噪点渐变国潮插画，国潮风格，主体简化为几何形态，保留少量细节，"
        "高饱和度高明度配色，摒弃原图的色彩，整体马卡龙（青橙）渐变为主，色彩过渡平滑柔和；"
        "营造手绘质感与温柔治愈氛围；构图均衡规整，靠色彩明暗渐变塑造空间层次；"
        "无硬边、无强烈轮廓线，无写实光影，干净清爽的矢量插画质感。"
        "保持原图主体内容与构图。"
    ),
    "City Pop 复古插画": (
        "将图片转为 City Pop 风格复古插画：1980 年代日式赛璐璐动画质感，高饱和霓虹色彩，"
        "粉橙渐变色调，平涂色块，粗黑轮廓线，干净利落的线条，强烈色彩对比，复古颗粒质感，"
        "无复杂光影，怀旧浪漫氛围，高清细节，8K。保持原图主体内容与构图。"
    ),
    "木刻版画风格": (
        "将图片转为木刻版画：线条疏密变化，欧式雕刻版画风格，线条干净利落，"
        "均匀排线表现明暗体积，刀刻肌理感强；对称饱满构图，手工木刻质感，复古高级质感，"
        "剔除原图细节，剔除原图色彩，使用高明度高饱和度马卡龙（黑白）渐变配色，"
        "无多余杂色，无文字，无水印，画面干净统一。保持原图主体内容与构图。"
    ),
    "噪点插画风格": (
        "将图片转为噪点渐变插画，极简抽象风格，建筑简化为几何形态，主体建筑保留少量细节，"
        "高饱和度高明度配色，摒弃原图的色彩，整体马卡龙（蓝粉）渐变为主，色彩过渡平滑柔和；"
        "叠加细微颗粒/噪点肌理，营造手绘质感与温柔治愈氛围；构图均衡规整，"
        "靠色彩明暗渐变塑造空间层次；无硬边、无强烈轮廓线，无写实光影，"
        "干净清爽的矢量插画质感，兼具现代都市氛围感与梦幻感。保持原图主体内容与构图。"
    ),
    "手绘涂鸦风格": (
        "将图片转为手绘涂鸦风格插画：蜡笔质感、粗线涂抹，粗糙随性的线条，"
        "带笔刷肌理毛边的涂抹效果，无平滑渐变，纸张肌理背景，粗蜡笔线条涂抹出主体，"
        "风格独特，乱线勾勒的轮廓，街头涂鸦感，儿童式潦草手绘风，剔除原图细节，剔除原图色彩，"
        "使用线条的疏密表达光影，2D 平面插画，有机手绘肌理，"
        "（米白色）背景和（蓝色）主体两个颜色，画面无文字信息。保持原图主体内容与构图。"
    ),
    "超现实波普拼贴": (
        "将图片转为超现实波普拼贴画（surreal pop collage）：主体去色成黑白保留为现实锚点，"
        "3 秒内能认出原图主体；背景用 2-3 个巨大平涂色形替换，颜色从原图主色提炼或互补撞色，"
        "平涂无渐变、无立体阴影；全图只保留一个不可能的巨物（把图内小元素放大到不合常理，"
        "或尺度颠倒，或场景语义最远的物件），除此之外不允许第二个超现实元素；"
        "成群小元素（飞鸟/落叶/纸船）3-5 个按大小梯度沿弧线分布，配 2-3 条白色手绘涂鸦线条；"
        "整体明亮，黑白现实与平涂梦境强烈对撞，画面干净，无文字、无水印。"
        "保持原图主体内容与构图。"
    ),
}

# 图生图（图像编辑）候选模型池；额度用完自动轮换
IMG2IMG_MODELS = [
    "qwen-image-edit-max",
    "qwen-image-edit-max-2026-01-16",
    "qwen-image-edit-plus",
    "qwen-image-edit-plus-2025-12-15",
    "qwen-image-edit-plus-2025-10-30",
]

# 图生图已耗尽的模型集合
_EDIT_EXHAUSTED_MODELS: set[str] = set()


def generate_edit(
    image_data_url: str, prompt: str, api_key: str = None, model: str = None,
    size: str = None, n: int = 1,
) -> list[str]:
    """图生图：把一张图按编辑指令重绘，返回多张新图 URL（n 张）。模型缺省用 IMAGE_EDIT_MODEL。"""
    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key")
    m = model or IMG2IMG_MODELS[0]
    n = min(max(int(n or 1), 1), 6)   # 官方支持 1~6 张

    def _call(out_size: str | None):
        kwargs = dict(
            api_key=key,
            model=m,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": image_data_url},
                        {"text": prompt},
                    ],
                }
            ],
            result_format="message",
            stream=False,
            watermark=False,
            prompt_extend=True,
            n=n,
        )
        if out_size:
            kwargs["size"] = out_size   # 官方参数：宽*高，如 "1024*2048"
        return MultiModalConversation.call(**kwargs)

    resp = _call(size)
    # 若指定尺寸不被该模型支持，去掉尺寸重试一次
    if resp.status_code != 200 and size:
        retry = _call(None)
        if retry.status_code == 200:
            resp = retry
    if resp.status_code != 200:
        raise QwenError(f"图生图失败 ({resp.status_code})：{getattr(resp, 'message', resp)}")
    content = resp.output.choices[0].message.content
    urls = [item["image"] for item in content if isinstance(item, dict) and item.get("image")]
    if not urls:
        raise QwenError("图生图结果中未找到图片 URL")
    return urls[:n]


def generate_edit_with_fallback(
    image_data_url: str, prompt: str, api_key: str = None, preferred_model: str = None,
    size: str = None, n: int = 1,
) -> tuple[list[str], str, str | None]:
    """图生图轮换：优先指定模型，额度用完自动换下一个；返回 (urls, used_model, note)。"""
    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key")
    order = _build_order(preferred_model, IMG2IMG_MODELS)
    urls, used, note = _rotate_with_fallback(
        order,
        _EDIT_EXHAUSTED_MODELS,
        lambda m: generate_edit(image_data_url, prompt, api_key=api_key, model=m, size=size, n=n),
        "所有图生图模型的额度均已耗尽：",
    )
    return urls, used, note
