"""千问 API 封装：qwen-plus 摘要 + qwen-image-3.0-pro 生图。

默认走阿里云百炼（大陆站）https://dashscope.aliyuncs.com/api/v1。
海外千问 AI 平台（platform.qianwenai.com）请在 .env 设置
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1。
Qwen-Image 不支持 OpenAI compatible-mode，必须走 DashScope 原生接口。
"""

import base64
import json
import os
import re

import dashscope
from dashscope import Generation, MultiModalConversation

SUMMARY_MODEL = "qwen-plus"
IMAGE_MODEL = "qwen-image-3.0-pro"


def _configure_base_url():
    url = os.getenv("DASHSCOPE_BASE_URL", "").strip().rstrip("/")
    dashscope.base_http_api_url = url or "https://dashscope.aliyuncs.com/api/v1"


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


def generate_poster(poster_prompt: str, size: str = "2048*2048", api_key: str = None) -> str:
    """同步生图，返回图片 URL。"""
    from prompt_builder import NEGATIVE_PROMPT

    key = _resolve_key(api_key)
    if not key:
        raise QwenError("缺少 API Key：请在页面填入，或配置 .env 中的 DASHSCOPE_API_KEY")
    resp = MultiModalConversation.call(
        api_key=key,
        model=IMAGE_MODEL,
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
