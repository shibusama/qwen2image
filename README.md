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
