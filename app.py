"""千问信息图海报 / 思维导图 Web 应用后端。"""

from pathlib import Path

from dotenv import load_dotenv

# 必须在 import qwen_client 之前加载 .env，否则 DASHSCOPE_BASE_URL 无法生效
load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import extract
import qwen_client
from prompt_builder import build_generation_pipeline

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="千问知识海报")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    """让页面与静态资源不缓存，改代码后刷新即生效，无需手动 bump 版本号。"""
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/models/available")
def models_available():
    """首页“生图模型”下拉框的数据源：可用候选池 + 默认模型（已剔除已知耗尽的模型）。"""
    return {
        "ok": True,
        "models": qwen_client.IMAGE_MODEL_CANDIDATES,
        "default": qwen_client.IMAGE_MODEL,
    }


@app.get("/api/img2img/styles")
def img2img_styles():
    """图生图页面的风格按钮数据源（风格名列表，描述由后端预置）。"""
    return {"ok": True, "styles": list(qwen_client.IMG2IMG_STYLES.keys())}


def _map_error(e: Exception) -> HTTPException:
    """把内部异常统一映射为 HTTP 错误：HTTPException 原样；QwenError→502；ValueError→400；其余→500。"""
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, qwen_client.QwenError):
        return HTTPException(502, str(e))
    if isinstance(e, ValueError):
        return HTTPException(400, str(e))
    return HTTPException(500, f"处理失败：{e}")


@app.post("/api/img2img")
def img2img(
    file: UploadFile = File(...),
    style: str = Form("美式波普风"),
    n: int = Form(1),
    api_key: str = Form(""),
):
    """图生图：上传一张图 + 风格 + 出图数量；输出尺寸默认与原图一致。"""
    import base64 as b64

    try:
        if not file:
            raise HTTPException(400, "请选择要上传的图片")
        raw = file.file.read()
        if not raw:
            raise HTTPException(400, "上传的图片为空")
        # 转成 base64 data URL 交给编辑模型
        mime = file.content_type or "image/png"
        data_url = f"data:{mime};base64,{b64.b64encode(raw).decode('ascii')}"

        style_name = style if style in qwen_client.IMG2IMG_STYLES else "美式波普风"
        prompt = qwen_client.IMG2IMG_STYLES[style_name]

        # 输出尺寸与原图一致；无法解析时由模型默认
        wh = extract.image_size(raw)
        out_size = f"{wh[0]}*{wh[1]}" if wh else None
        n = min(max(int(n or 1), 1), 6)

        image_urls, used_model, note = qwen_client.generate_edit_with_fallback(
            data_url, prompt, api_key=api_key, size=out_size, n=n
        )
        result = {
            "ok": True,
            "images": image_urls,
            "used_model": used_model,
            "style": style_name,
            "size": out_size or "default",
            "n": len(image_urls),
        }
        if note:
            result["note"] = note
        return result
    except Exception as e:
        raise _map_error(e)


def _extract_source(mode: str, content: str, url: str, file) -> str:
    if mode == "file":
        if not file:
            raise HTTPException(400, "请选择要上传的文件")
        raw = file.file.read()
        source_text = extract.extract_file_bytes(file.filename or "", raw)
    elif mode == "url":
        if not url.strip():
            raise HTTPException(400, "请输入要抓取的 URL")
        source_text = extract.extract_url(url.strip())
    else:  # text
        if not content.strip():
            raise HTTPException(400, "请粘贴要转换的文本")
        source_text = content.strip()
    if len(source_text) < 10:
        raise HTTPException(400, "内容太短，无法生成")
    return source_text


@app.post("/api/generate")
def generate(
    mode: str = Form(...),
    content: str = Form(""),
    url: str = Form(""),
    size: str = Form("portrait"),
    style: str = Form("creative-long"),
    type: str = Form("poster"),
    api_key: str = Form(""),
    model: str = Form(""),
    file: UploadFile = File(None),
):
    # 注意：这里保持同步 def（FastAPI 会放入线程池执行），
    # 因为千问摘要/生图是同步阻塞调用，async def 会卡死事件循环。
    try:
        source_text = _extract_source(mode, content, url, file)

        # 模型与 API Key 写死在 qwen_client，直接调用；api_key 传了则覆盖
        kind = "mindmap" if type == "mindmap" else "poster"
        summary = qwen_client.summarize(source_text, api_key=api_key, kind=kind)

        prompt, size_pixels = build_generation_pipeline(kind, summary, size, style)

        image_url, used_model, switch_note = qwen_client.generate_poster_with_fallback(
            prompt,
            size=size_pixels,
            api_key=api_key,
            preferred_model=model,   # 首页下拉选定的生图模型（可选）
        )
        data_url = qwen_client.image_to_base64(image_url)
        result = {
            "ok": True,
            "image_base64": data_url,
            "image_url": image_url,
            "summary": summary,
            "used_model": used_model,
        }
        if switch_note:
            result["note"] = switch_note   # 额度用完切模型时的提示
        return result
    except Exception as e:
        raise _map_error(e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
