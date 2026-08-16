"""管理端模型配置存储：对象存储持久化 models.json。

存储方式：
- 优先使用对象存储（S3 兼容，环境变量 COZE_BUCKET_ENDPOINT_URL / COZE_BUCKET_NAME）
- 对象存储 key 带时间戳（models/models.json_<ts>_<hash>.json），list 字典序即新旧序，
  读取时取最新版本并清理旧版本，避免 SDK 随机 key 无法定位的问题
- 未配置对象存储环境变量时（本地开发），回退本地文件 data/models.json

数据格式：
    {"models": [{"id": 1, "name": "qwen-plus", "api_key": "sk-xxx",
                 "remark": "备注", "created_at": "2026-..."}]}
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from coze_coding_dev_sdk.s3 import S3SyncStorage

CONFIG_PREFIX = "models/models.json_"
CONFIG_MARK = "models.json_"  # key 中文件名部分标记（key 带 coze_storage_<id>/ 前缀，用文件名匹配）
# 仅匹配正式配置文件名：models.json_<时间戳>_<8位hex>.json（排除 probe 等垃圾文件）
CONFIG_RE = re.compile(r"models\.json_\d{14,25}_[0-9a-f]{8}\.json$")
MAX_KEEP = 3  # 对象存储中保留的最新版本数（超过的旧版本删除）
CACHE_TTL = 30.0  # 进程内缓存有效期（秒）

# 进程内缓存：规避对象存储 list 写后延迟（刚写入的对象立即可见，但 list 索引可能秒级延迟）
_models_cache: list[dict] | None = None
_cache_ts: float = 0.0


def _set_cache(models: list[dict]) -> None:
    global _models_cache, _cache_ts
    _models_cache = models
    _cache_ts = time.time()


def _strip_prefix(key: str) -> str:
    """list_files 返回的 key 带 coze_storage_<id>/ 前缀，read/delete 需要裸 key。"""
    if key.startswith("coze_storage_"):
        idx = key.find("/")
        if idx != -1:
            return key[idx + 1 :]
    return key


def _get_storage() -> S3SyncStorage | None:
    """返回对象存储客户端；未配置环境变量时返回 None（走本地文件兜底）。"""
    endpoint = os.getenv("COZE_BUCKET_ENDPOINT_URL", "")
    bucket = os.getenv("COZE_BUCKET_NAME", "")
    if endpoint and bucket:
        return S3SyncStorage(
            endpoint_url=endpoint,
            access_key="",  # SDK 从环境变量读取密钥
            secret_key="",
            bucket_name=bucket,
            region="cn-beijing",
        )
    return None


def _local_file() -> Path:
    """本地兜底文件路径：开发环境项目 data/；生产只读时回退 /tmp。"""
    base = Path(__file__).resolve().parent / "data"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base / "models.json"
    except OSError:
        return Path("/tmp") / "models.json"


def _read_raw() -> str | None:
    """读取最新配置原文；无配置时返回 None。"""
    storage = _get_storage()
    if storage is not None:
        try:
            result = storage.list_files(prefix=CONFIG_PREFIX)
            keys = [k for k in (result.get("keys") or []) if CONFIG_RE.search(k)]
            if not keys:
                return None
            latest = max(keys)  # 时间戳在 key 中，字典序最大 = 最新
            data = storage.read_file(file_key=_strip_prefix(latest))
            return data.decode("utf-8")
        except Exception:
            return None
    p = _local_file()
    if p.exists():
        try:
            return p.read_text("utf-8")
        except OSError:
            return None
    return None


def _write_raw(text: str) -> None:
    """写入配置（对象存储写新版本并清理旧版，本地直接覆盖）。"""
    storage = _get_storage()
    if storage is not None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        storage.upload_file(
            file_content=text.encode("utf-8"),
            file_name=f"{CONFIG_PREFIX}{ts}.json",
            content_type="application/json",
        )
        # 清理旧版本与垃圾文件：保留最新 MAX_KEEP 个合规版本，其余全部删除
        try:
            result = storage.list_files(prefix=CONFIG_PREFIX)
            all_keys = sorted(k for k in (result.get("keys") or []) if CONFIG_MARK in k)
            keep = [k for k in all_keys if CONFIG_RE.search(k)][-MAX_KEEP:]
            for old in all_keys:
                if old not in keep:
                    storage.delete_file(file_key=_strip_prefix(old))
        except Exception:
            pass
    else:
        _local_file().write_text(text, "utf-8")


def list_models() -> list[dict]:
    """返回全部模型配置（含 api_key 明文，仅供后端使用）。优先走进程内缓存。"""
    global _models_cache, _cache_ts
    if _models_cache is not None and time.time() - _cache_ts < CACHE_TTL:
        return _models_cache
    raw = _read_raw()
    if not raw:
        models: list[dict] = []
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            models = []
        else:
            raw_models = data.get("models") if isinstance(data, dict) else None
            models = raw_models if isinstance(raw_models, list) else []
    _set_cache(models)
    return models


def add_model(name: str, api_key: str, remark: str = "") -> dict:
    """新增模型配置，返回完整记录。"""
    models = list_models()
    next_id = max((m.get("id", 0) for m in models), default=0) + 1
    record = {
        "id": next_id,
        "name": name.strip(),
        "api_key": api_key.strip(),
        "remark": remark.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    models.append(record)
    _write_raw(json.dumps({"models": models}, ensure_ascii=False, indent=2))
    _set_cache(models)  # 写后立即更新缓存，规避对象存储 list 写后延迟
    return record


def delete_model(model_id: int) -> bool:
    """按 id 删除模型配置；不存在返回 False。"""
    models = list_models()
    new_models = [m for m in models if m.get("id") != model_id]
    if len(new_models) == len(models):
        return False
    _write_raw(json.dumps({"models": new_models}, ensure_ascii=False, indent=2))
    _set_cache(new_models)  # 写后立即更新缓存
    return True


def resolve_model_name(default_model: str) -> str:
    """生成时取模型名：管理端有配置时用第一条的模型名，否则回退默认值（.env / 内置）。

    与管理端 Key 解析保持同一优先级（第一条配置优先），保证"首页显示"与"实际调用"一致。
    """
    for m in list_models():
        name = (m.get("name") or "").strip()
        if name:
            return name
    return default_model


def resolve_api_key(preferred_model: str | None = None) -> str | None:
    """生成时取 Key：优先匹配指定模型名的配置 → 任意第一条 → None（回退 .env）。

    摘要与生图共用一个 DashScope 账户 Key，因此通常传 None 取第一条即可。
    """
    models = list_models()
    if preferred_model:
        for m in models:
            if m.get("name") == preferred_model and m.get("api_key"):
                return m["api_key"]
    for m in models:
        if m.get("api_key"):
            return m["api_key"]
    return None
