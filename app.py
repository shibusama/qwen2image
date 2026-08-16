"""千问信息图海报 / 思维导图 Web 应用后端。"""

from pathlib import Path

from dotenv import load_dotenv

# 必须在 import qwen_client 之前加载 .env，否则 DASHSCOPE_BASE_URL / IMAGE_MODEL 无法生效
load_dotenv()

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import extract
import models_store
import qwen_client
from prompt_builder import STYLES, build_mindmap_prompt, build_poster_prompt

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


@app.get("/api/models/list")
def models_list(api_key: str = ""):
    """拉取某个 API Key 可用的模型列表（按文本 / 视觉分类）。

    用于管理端"输入 Key 自动带出模型"：传 ?api_key=xxx 或省略用 .env。
    """
    try:
        return {"ok": True, **qwen_client.list_models(api_key or None)}
    except qwen_client.QwenError as e:
        raise HTTPException(400, str(e))


@app.get("/api/models/config")
def models_config():
    """返回当前摘要模型与生图模型名称（仅来自管理端配置，未配置则返回空字符串）。"""
    return {
        "ok": True,
        "summary_model": models_store.resolve_model_name(model_type="text") or "",
        "image_model": models_store.resolve_model_name(model_type="vision") or "",
    }


@app.get("/admin")
def admin_page():
    """管理端页面：添加/管理模型名称与 API Key。"""
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/api/admin/models")
def admin_list_models():
    """模型配置列表（API Key 脱敏返回）。"""
    models = models_store.list_models()
    for m in models:
        key = m.get("api_key", "") or ""
        m["api_key_masked"] = key[:6] + "****" + key[-4:] if len(key) > 10 else "****"
        m.pop("api_key", None)
    return {"ok": True, "models": models}


@app.post("/api/admin/models")
def admin_add_model(payload: dict = Body(...)):
    """新增模型配置（模型名称 + API Key + 类型 + 备注），JSON body。"""
    name = (payload.get("name") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    remark = (payload.get("remark") or "").strip()
    model_type = (payload.get("model_type") or "").strip()
    if not name:
        raise HTTPException(400, "模型名称不能为空")
    if not api_key:
        raise HTTPException(400, "API Key 不能为空")
    if model_type not in ("text", "vision"):
        raise HTTPException(400, "模型类型必须是 text（文本/摘要）或 vision（视觉/生图）")
    record = models_store.add_model(name, api_key, remark, model_type)
    return {"ok": True, "model": record}


@app.delete("/api/admin/models/{model_id}")
def admin_delete_model(model_id: int):
    """删除模型配置。"""
    if not models_store.delete_model(model_id):
        raise HTTPException(404, "模型配置不存在")
    return {"ok": True}


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
    file: UploadFile = File(None),
):
    # 注意：这里保持同步 def（FastAPI 会放入线程池执行），
    # 因为千问摘要/生图是同步阻塞调用，async def 会卡死事件循环。
    try:
        source_text = _extract_source(mode, content, url, file)

        # 严格模式：模型与 Key 只来自管理端配置，未配置直接报错（不回退 .env）
        summary_model = models_store.resolve_model_name(model_type="text")
        vision_model = models_store.resolve_model_name(model_type="vision")
        if not summary_model:
            raise HTTPException(400, "未配置文本模型（摘要用），请先到管理端添加")
        if not vision_model:
            raise HTTPException(400, "未配置视觉模型（生图用），请先到管理端添加")

        summary_key = api_key or models_store.resolve_api_key(model_type="text")
        vision_key = api_key or models_store.resolve_api_key(model_type="vision")
        if not summary_key:
            raise HTTPException(400, "文本模型缺少 API Key，请到管理端补充")
        if not vision_key:
            raise HTTPException(400, "视觉模型缺少 API Key，请到管理端补充")

        kind = "mindmap" if type == "mindmap" else "poster"
        summary = qwen_client.summarize(
            source_text, api_key=summary_key, kind=kind, model=summary_model
        )

        aspect = size if size in qwen_client.SIZES else "square"
        style = style if style in STYLES else "creative-long"
        if kind == "mindmap":
            prompt = build_mindmap_prompt(summary, aspect, style)
        else:
            prompt = build_poster_prompt(summary, aspect, style)

        image_url = qwen_client.generate_poster(
            prompt,
            size=qwen_client.SIZES[aspect],
            api_key=vision_key,
            model=vision_model,
        )
        data_url = qwen_client.image_to_base64(image_url)
        return {
            "ok": True,
            "image_base64": data_url,
            "image_url": image_url,
            "summary": summary,
        }
    except HTTPException:
        raise
    except qwen_client.QwenError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(500, f"处理失败：{e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
