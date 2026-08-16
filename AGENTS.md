# AGENTS.md

## 项目概览

千问知识海报生成网站（Qwen2Image）。用户输入文本 / URL / 文件，后端用千问大模型（qwen-plus 摘要 + qwen-image 生图）生成信息图海报或思维导图。

技术栈：Python + FastAPI + Uvicorn，前端为原生 HTML/CSS/JS（`static/`）。

## 常用命令

```bash
# 开发运行（监听 ${DEPLOY_RUN_PORT}，默认 5000）
sh -c "python -m uvicorn app:app --host 0.0.0.0 --port ${DEPLOY_RUN_PORT:-5000}"

# 依赖安装
python -m pip install -r requirements.txt
```

## 代码结构

| 文件 | 职责 |
|------|------|
| `app.py` | FastAPI 入口：首页静态服务、`POST /api/generate` 生成接口、`/admin` 管理端、`/api/admin/models` CRUD |
| `qwen_client.py` | 千问 API 封装：`summarize`（文本摘要）、`generate_poster`（海报/导图生图），模型与 Key 来自 `.env` |
| `prompt_builder.py` | 摘要转海报/导图 prompt（8 种风格 STYLES） |
| `extract.py` | 上传文件（PDF/Word）文本提取 |
| `models_store.py` | 管理端模型配置存储：对象存储（`models/models.json_<ts>`）+ 进程内缓存 + 本地文件兜底 |
| `static/index.html` | 首页：输入内容 → 生成海报 |
| `static/admin.html` | 管理端：添加/删除模型（文本型/视觉型）+ API Key，支持按 Key 拉取可用模型列表 |
| `static/app.js` / `style.css` | 首页交互与样式 |

## 关键逻辑

- **模型与 Key（唯一来源是管理端，无回退）**：请求带 `api_key` → 用它；否则从管理端按类型取（文本型用于摘要、视觉型用于生图，取该类型第一条）
  - 摘要模型 = 管理端文本型配置的 name；生图模型 = 管理端视觉型配置的 name
  - **任一类型未配置或缺 Key → 直接报错**（如"文本模型缺少 API Key，请到管理端补充"），不回退 `.env`
  - `.env` 的 `DASHSCOPE_API_KEY` 仅作为兜底（管理端完全没有配置时）
- **模型列表拉取**：`GET /api/models/list` 调 DashScope `/compatible-mode/v1/models` 按 Key 拉取全部可用模型，按名称关键词分类为 `text`（摘要）与 `vision`（生图）
  - 视觉模型必须选**文生图**模型（`qwen-image-3.0` / `qwen-image-max` 等）；**`qwen-image-edit-*` 是图像编辑模型，不能文生图**（报 "must contain 1~3 image content items"）
  - 文本模型注意：`qwq-*` 推理模型只支持流式（非流式报 400），`summarize` 已实现自动流式重试
- **对象存储**：配置持久化到 S3 兼容对象存储（`COZE_BUCKET_*` 环境变量），每次写入生成带时间戳的新对象，读取取最新并清理旧版本
- **重要**：`list_files` 返回的 key 带 `coze_storage_<id>/` 前缀，读写前必须剥离；`read_file` 需传裸 key
- **写后一致性**：对象存储 list 有秒级延迟，models_store 用进程内缓存（TTL 30s）保证写后读一致

## 环境变量（.env）

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_BASE_URL` | API 地址，大陆 `https://dashscope.aliyuncs.com/api/v1`；海外 `https://dashscope-intl.aliyuncs.com/api/v1`（必需） |
| `DASHSCOPE_API_KEY` | 千问 API Key，仅用于 `/api/models/list` 未传 Key 时兜底拉取模型列表；实际生成模型与 Key 一律来自管理端 |

`.env` 已被 gitignore，密钥不入库；`data/` 目录同理。

## 注意事项

- 生图为同步接口，单张约 1~3 分钟，前端需等待
- 管理端当前无鉴权，公开部署需自行加密码/限流
- 生产环境（vefaas）唯一可写目录为 `/tmp`，模型配置存对象存储不依赖本地文件
- 部署命令在 `.coze`（deploy.run 必须用裸数组，`sh -c exec` 会导致 vefaas 启动失败）
