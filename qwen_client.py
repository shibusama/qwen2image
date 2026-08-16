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
from urllib.parse import urlparse

import dashscope
from dashscope import Generation, MultiModalConversation

# 兜底 API 地址（千问平台）；实际以 .env 中 DASHSCOPE_BASE_URL 为准
DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/api/v1"

# 摘要模型；可在 .env 用 SUMMARY_MODEL=... 覆盖（如 qwen-max / qwen-turbo）
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL") or "qwen-plus"
# 默认生图模型；可在 .env 用 IMAGE_MODEL=... 覆盖（推荐 qwen-image-max 最强）
IMAGE_MODEL = os.getenv("IMAGE_MODEL") or "qwen-image-3.0"


def _configure_base_url():
    # 从 .env 读取，不写死；缺失时回退 DEFAULT_BASE_URL
    url = os.getenv("DASHSCOPE_BASE_URL", "").strip().rstrip("/")
    dashscope.base_http_api_url = url or DEFAULT_BASE_URL


_configure_base_url()

SIZES = {
    "square": "2048*2048",
    "landscape": "2048*1152",
    "portrait": "1152*2048",
}


class QwenError(Exception):
    pass


def _resolve_key(api_key):
    if api_key and api_key.strip():
        return api_key.strip()
    return os.getenv("DASHSCOPE_API_KEY") or ""


# 视觉（生图/图像编辑）模型特征关键词
VISION_KEYWORDS = ("image", "wan2", "z-image", "flux", "picture", "draw")
# 与文本摘要/生图无关的模型类型，列表拉取时排除
IRRELEVANT_KEYWORDS = (
    "audio", "tts", "asr", "speech", "realtime", "embedding", "ocr",
    "translate", "s2s", "video", "live2d", "mt-",
)


def list_models(api_key: str = None) -> dict:
    """拉取当前 Key 可用的 DashScope 模型列表，按文本 / 视觉分类。

    返回 {"text": [...], "vision": [...]}；失败时抛 QwenError。
    """
    import requests

    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key，无法拉取模型列表")
    base = (os.getenv("DASHSCOPE_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(base)
    url = f"{parsed.scheme}://{parsed.netloc}/compatible-mode/v1/models"
    resp = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=15)
    if resp.status_code != 200:
        raise QwenError(f"拉取模型列表失败 ({resp.status_code})：{resp.text[:200]}")
    ids = [m.get("id") for m in (resp.json().get("data") or []) if m.get("id")]
    text, vision = [], []
    for mid in ids:
        low = mid.lower()
        if any(k in low for k in VISION_KEYWORDS):
            vision.append(mid)
        elif any(k in low for k in IRRELEVANT_KEYWORDS):
            continue
        else:
            text.append(mid)
    return {"text": sorted(text), "vision": sorted(vision)}


def summarize(source_text: str, api_key: str = None, kind: str = "poster") -> dict:
    """用 qwen-plus 把原文提炼成结构化 JSON（poster=信息图，mindmap=思维导图）。"""
    from prompt_builder import build_summary_mindmap_prompt, build_summary_prompt

    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key：请在页面填入，或配置 .env 中的 DASHSCOPE_API_KEY")
    prompt = (
        build_summary_mindmap_prompt(source_text)
        if kind == "mindmap"
        else build_summary_prompt(source_text)
    )
    resp = Generation.call(
        api_key=key,
        model=SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        result_format="message",
    )
    if resp.status_code != 200:
        raise QwenError(f"摘要失败 ({resp.status_code})：{getattr(resp, 'message', resp)}")
    text = resp.output.choices[0].message.content
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
        raise QwenError("缺少 API Key：请在页面填入，或配置 .env 中的 DASHSCOPE_API_KEY")
    resp = MultiModalConversation.call(
        api_key=key,
        model=model or IMAGE_MODEL,
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
