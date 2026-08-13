"""千问信息图海报 / 思维导图 Web 应用后端。"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import extract
import qwen_client
from prompt_builder import STYLES, build_mindmap_prompt, build_poster_prompt

load_dotenv()

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
    size: str = Form("square"),
    style: str = Form("creative-long"),
    type: str = Form("poster"),
    api_key: str = Form(""),
    file: UploadFile = File(None),
):
    # 注意：这里保持同步 def（FastAPI 会放入线程池执行），
    # 因为千问摘要/生图是同步阻塞调用，async def 会卡死事件循环。
    try:
        source_text = _extract_source(mode, content, url, file)

        kind = "mindmap" if type == "mindmap" else "poster"
        summary = qwen_client.summarize(source_text, api_key=api_key, kind=kind)

        aspect = size if size in qwen_client.SIZES else "square"
        style = style if style in STYLES else "creative-long"
        if kind == "mindmap":
            prompt = build_mindmap_prompt(summary, aspect, style)
        else:
            prompt = build_poster_prompt(summary, aspect, style)

        image_url = qwen_client.generate_poster(
            prompt,
            size=qwen_client.SIZES[aspect],
            api_key=api_key,
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
