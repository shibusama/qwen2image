# AGENTS.md

## 项目概览

千问知识海报生成网站（Qwen2Image）。后端用千问大模型（qwen-plus 摘要 + qwen-image 系列生图 / qwen-image-edit 系列图生图）把文本/URL/文件转成信息图海报或思维导图，也支持上传图片按风格重绘（图生图）。

技术栈：Python + FastAPI + Uvicorn，前端为原生 HTML/CSS/JS（`static/`），无构建依赖。

## 常用命令

```bash
# 开发运行（默认 8002；8000/8001 在本机常被系统隐性占用，绑定会报 10048）
python -m uvicorn app:app --host 127.0.0.1 --port 8002

# 依赖安装
python -m pip install -r requirements.txt
```

## 代码结构

| 文件 | 职责 |
|------|------|
| `app.py` | FastAPI 入口：页面服务（`/`、`/api/models/available`）、`POST /api/generate`（文生图）、`POST /api/img2img`（图生图）、`/api/img2img/styles`；含 `_image_size`（PNG/JPEG 原图尺寸解析） |
| `qwen_client.py` | 千问 API 封装：写死配置（URL/Key/模型/候选池）、`summarize`、`generate_poster_with_fallback`（文生图+额度轮换）、`generate_edit_with_fallback`（图生图+额度轮换）、`IMG2IMG_STYLES`（图生图风格描述）、`image_to_base64` |
| `prompt_builder.py` | 摘要/海报/思维导图 prompt 模板（8 种风格 STYLES、NEGATIVE_PROMPT） |
| `extract.py` | 上传文件（PDF/Word/TXT/MD）文本提取、URL 抓取 |
| `static/index.html` | 单页双 Tab：文生图（文本/文件/URL→海报/导图）+ 图生图（上传图→风格重绘） |
| `static/app.js` / `style.css` | 前端交互与样式 |

## 关键逻辑

- **配置写死在代码里**（`qwen_client.py` 顶部常量）：
  - `DEFAULT_BASE_URL` = 大陆原生端点；`_configure_base_url()` 优先读 `.env` 的 `DASHSCOPE_BASE_URL`，回退该写死值
  - `DASHSCOPE_API_KEY` = 写死的 Key（生成时 `_resolve_key` 优先用请求传入的 key，否则用该写死值）
  - `IMAGE_MODEL` / `IMAGE_MODEL_CANDIDATES` = 文生图默认模型与候选池
  - `IMG2IMG_MODELS` = 图生图（图像编辑）候选池；`IMG2IMG_STYLES` = 图生图风格 → 编辑指令（描述写死后端，前端只给风格名）
- **额度轮换**：`generate_poster_with_fallback`（文生图）与 `generate_edit_with_fallback`（图生图）——优先用候选池里未耗尽的模型；调用返回"额度不足"类错误（`_is_quota_error` 识别）即标记该模型耗尽并换下一个；非额度错误如实抛出；全部耗尽才报错。耗尽集合为进程内 `_EXHAUSTED_MODELS` / `_EDIT_EXHAUSTED_MODELS`。
- **文生图流程**（`/api/generate`）：文本/URL/文件 → `qwen_client.summarize`（qwen-plus 提炼 JSON）→ `prompt_builder` 组 prompt → `generate_poster_with_fallback` 生图 → 返回 `{ok, image_base64, image_url, summary, used_model, note?}`。表单字段：`mode`(text/url/file) + 对应输入 + `size`(square/landscape/portrait) + `style` + `type`(poster/mindmap) + `model`(可选，首页下拉选中的生图模型) + `api_key`(可选)。
- **图生图流程**（`/api/img2img`）：上传图片 → 读原图宽高作输出尺寸（`_image_size`）→ 按所选风格的写死指令 → `generate_edit_with_fallback` 重绘 → 返回 `{ok, images:[url...], used_model, style, size, n, note?}`。表单字段：`file` + `style` + `n`(1~6，一次出几张) + `api_key`。
- **额度耗尽模型需从候选池剔除**：已知耗尽的模型（如 `qwen-image-3.0`）不要出现在 `IMAGE_MODEL_CANDIDATES` / `IMG2IMG_MODELS`，避免空试；用户确认某模型耗尽后，从对应池删除即可（前端下拉自动同步，因为 `/api/models/available` 和 `/api/img2img/styles` 读的就是这些池）。

## 环境变量（.env）

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_BASE_URL` | API 地址：大陆 `https://dashscope.aliyuncs.com/api/v1`；海外 `https://dashscope-intl.aliyuncs.com/api/v1`（缺省用写死的大陆端点） |

密钥与模型名均已写死进 `qwen_client.py`，`.env` 不存任何密钥；`.env` 已被 gitignore。

## 注意事项

- 生图为同步接口：文生图单张约 30~60 秒，图生图 30~90 秒（多张更久），前端需等待；生图消耗账户额度。
- `qwen-image-edit-*` 是图像编辑模型（图生图），不能直接文生图；`generate_poster` 对含 "edit" 的模型会直接拒绝。
- 图生图输出尺寸默认与原图一致（`_image_size` 解析 PNG/JPEG 宽高；超大图可能被模型按能力调整）。
- 前端静态资源无缓存（middleware），改前端刷新即生效；改后端需重启 uvicorn。
