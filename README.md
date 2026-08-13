# 千问知识海报 · Qwen2Image

把一份文档 / 一段文本，变成一张**信息图海报**或**思维导图**。

由 `qwen-plus` 提炼核心要点，`qwen-image-3.0-pro` 排版成图。

## 功能

- **两种输出**：信息图海报、思维导图（中心 + 放射分支）
- **三种输入**：粘贴文本、上传文档（PDF / DOCX / TXT / MD）、抓取网页链接
- **8 种设计风格**：创意长图（默认）、蒸汽波、现代渐变、杂志编辑、手绘插画、暗色霓虹、复古报纸、极简瑞士
- **三种版式**：方图 1:1、横图 16:9、竖图 9:16
- 生成结果在线预览 + 一键下载 PNG

## 快速开始

```bash
cd qwen-infographic
pip install -r requirements.txt
```

复制 `.env.example` 为 `.env` 并填入你的 API Key：

```env
# 海外千问 AI 平台：https://platform.qianwenai.com/home/api-keys 创建 Key
DASHSCOPE_API_KEY=sk-xxx
# 海外平台填下面这行；大陆阿里云百炼留空即可
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1
```

启动：

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://localhost:8000> 即可使用。

## Docker 部署（推荐用于服务器/生产）

项目已内置 `Dockerfile` 与 `docker-compose.yml`，可直接容器化部署：

```bash
# 1. 准备环境变量（复制模板并填入 API Key）
cp .env.example .env

# 2. 构建并启动
docker compose up -d --build

# 3. 查看状态 / 日志 / 停止
docker compose ps
docker compose logs -f
docker compose down
```

访问 `http://<服务器IP>:5000`（宿主机端口可通过 `.env` 中 `PORT=8080` 修改）。

单容器方式（不用 compose）：

```bash
docker build -t qwen-infographic .
docker run -d --name qwen-infographic -p 5000:5000 --env-file .env --restart unless-stopped qwen-infographic
```

配置说明：

- `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` 通过 `.env` 注入容器（compose 自动读取；`.env` 缺失时服务也能启动，生成时在页面填写 Key 即可）
- 容器内监听端口由环境变量 `DEPLOY_RUN_PORT` 控制，默认 `5000`；宿主机端口由 compose 的 `${PORT:-5000}` 控制
- 镜像以非 root 用户运行，`.dockerignore` 已排除 `.env` / `.git`，避免敏感信息入镜像
- 如需更换模型/尺寸等，直接改 `qwen_client.py` 后 `docker compose up -d --build` 重建即可

## 使用说明

1. 选择输入方式：粘贴文本 / 上传文档 / 抓取链接
2. 选择输出类型：信息图海报 或 思维导图
3. 选择版式与风格（API Key 可留空，使用 `.env` 中的配置）
4. 点击生成，约 30~60 秒后预览并下载

## 技术栈

- 后端：FastAPI + DashScope SDK（千问）
- 模型：`qwen-plus`（摘要提炼）、`qwen-image-3.0-pro`（生图）
- 文档解析：`pypdfium2`（PDF）、`python-docx`（DOCX）
- 前端：原生 HTML / CSS / JS，无构建依赖

## 目录结构

```
qwen-infographic/
  app.py             # FastAPI 后端
  qwen_client.py     # 千问 API 封装（摘要 + 生图）
  prompt_builder.py  # 摘要 / 海报 / 思维导图 prompt 模板
  extract.py         # 文档 / URL 文本提取
  requirements.txt
  .env.example       # 环境变量模板（Key 请填进 .env，勿提交）
  static/            # 前端页面
```

## 说明

- 千问文生图走 DashScope 原生接口，**不支持 OpenAI 兼容模式**
- API Key 只保存在本地 `.env`，请勿提交到仓库
- 生图消耗账户额度，交互式生成前请确认余额充足
