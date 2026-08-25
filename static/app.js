const $ = (id) => document.getElementById(id);

let currentFeature = "text2img";
let currentMode = "text";
let currentType = "poster";
let lastDataUrl = "";
let imageModel = "";   // 文生图选定的生图模型
let selectedStyle = ""; // 图生图选定的风格

// ============ 通用小件 ============

// 状态显示（error 加红）
function setStatusEl(el, text, isError) {
  el.textContent = text;
  el.className = "status" + (isError ? " error" : "");
}

// 从后端拉列表填充 <select>：url 返回 {items 或 models, default?}
async function loadSelect(selId, url, field, emptyMsg, onValue) {
  const sel = $(selId);
  const update = () => { if (onValue) onValue(sel.value); };
  sel.addEventListener("change", update);
  try {
    const resp = await fetch(url);
    const data = await resp.json();
    const items = Array.isArray(data[field])
      ? data[field]
      : (Array.isArray(data.models) ? data.models : null);
    if (items && items.length) {
      sel.innerHTML = items.map((it) => `<option value="${it}">${it}</option>`).join("");
      sel.value = data.default || items[0];
      update();
    } else {
      sel.innerHTML = `<option value="">${emptyMsg}</option>`;
      sel.disabled = true;
    }
  } catch {
    sel.innerHTML = `<option value="">${emptyMsg}</option>`;
  }
}

// 通用提交流程：POST multipart → 校验/错误处理 → render(data)
async function runFlow(cfg) {
  const statusEl = $(cfg.statusId);
  const setBusy = (b) => cfg.btnIds.forEach((id) => { $(id).disabled = b; });
  const err = cfg.validate();
  if (err) { setStatusEl(statusEl, err, true); return; }
  setBusy(true);
  setStatusEl(statusEl, cfg.runningMsg, false);
  try {
    const resp = await fetch(cfg.url, { method: "POST", body: cfg.buildFd() });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      setStatusEl(statusEl, data.detail || "生成失败", true);
      return;
    }
    cfg.render(data, statusEl);
  } catch (e) {
    setStatusEl(statusEl, "网络错误：" + e.message, true);
  } finally {
    setBusy(false);
  }
}

// ============ 功能 Tab：文生图 / 图生图 ============
document.querySelectorAll("[data-feature]").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll("[data-feature]").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentFeature = tab.dataset.feature;
    document.querySelectorAll(".feature-panel").forEach((p) =>
      p.classList.toggle("hidden", p.dataset.featurePanel !== currentFeature)
    );
  });
});

// ============ 文生图 ============

// 生图模型下拉（后端候选池，已剔除额度耗尽的模型）
loadSelect("imageModel", "/api/models/available", "models", "（当前无可用生图模型）",
  (v) => { imageModel = v; });

// 输入方式 Tab
document.querySelectorAll(".tab[data-mode]").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab[data-mode]").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentMode = tab.dataset.mode;
    document.querySelectorAll(".panel").forEach((p) =>
      p.classList.toggle("hidden", p.dataset.panel !== currentMode)
    );
  });
});

// 上传文档后显示文件名
$("file").addEventListener("change", () => {
  const f = $("file").files[0];
  const label = document.querySelector(".panel[data-panel='file'] .drop span");
  if (f) label.textContent = "已选择：" + f.name;
});

// 类型卡片切换（海报 / 导图）
const typeLabels = { poster: "生成信息图海报", mindmap: "生成思维导图" };
document.querySelectorAll(".type-card[data-type]").forEach((card) => {
  card.addEventListener("click", () => {
    document.querySelectorAll(".type-card[data-type]").forEach((c) => c.classList.remove("active"));
    card.classList.add("active");
    currentType = card.dataset.type;
    $("go").textContent = typeLabels[currentType] || "生成";
  });
});

function buildFormData() {
  const fd = new FormData();
  fd.append("mode", currentMode);
  fd.append("size", $("size").value);
  fd.append("style", $("style").value);
  fd.append("type", currentType);
  if (imageModel) fd.append("model", imageModel);
  if (currentMode === "file") {
    const f = $("file").files[0];
    if (f) fd.append("file", f);
  } else if (currentMode === "url") {
    fd.append("url", $("url").value.trim());
  } else {
    fd.append("content", $("content").value);
  }
  return fd;
}

function validateText2img() {
  if (currentMode === "file" && !$("file").files[0]) return "请选择要上传的文件";
  if (currentMode === "url" && !$("url").value.trim()) return "请输入要抓取的链接";
  if (currentMode === "text" && !$("content").value.trim()) return "请粘贴要转换的文本";
  return "";
}

function runText2img() {
  return runFlow({
    url: "/api/generate",
    buildFd: buildFormData,
    validate: validateText2img,
    runningMsg: "正在提炼并生成，约需 30~60 秒…",
    statusId: "status",
    btnIds: ["go", "again"],
    render(data, el) {
      lastDataUrl = data.image_base64;
      $("preview").src = lastDataUrl;
      $("download").href = lastDataUrl;
      $("download").setAttribute("download", "output.png");
      $("download").textContent = "下载图片";
      $("result").classList.remove("hidden");
      setStatusEl(
        el,
        data.note
          ? data.note
          : ("生成完成" + (data.used_model ? "，模型 " + data.used_model : ""))
      );
    },
  });
}

$("go").addEventListener("click", runText2img);
$("again").addEventListener("click", runText2img);

// ============ 图生图 ============

// 风格下拉（描述写死后端）
loadSelect("imgStyle", "/api/img2img/styles", "styles", "（风格加载失败）",
  (v) => { selectedStyle = v; });

$("imgFile").addEventListener("change", () => {
  const f = $("imgFile").files[0];
  const label = document.querySelector(".feature-panel[data-feature-panel='img2img'] .drop span");
  if (f) label.textContent = "已选择：" + f.name;
});

function buildImg2imgFd() {
  const fd = new FormData();
  fd.append("file", $("imgFile").files[0]);
  fd.append("style", selectedStyle);
  fd.append("n", $("imgN").value);
  return fd;
}

function validateImg2img() {
  if (!$("imgFile").files[0]) return "请先选择要重绘的图片";
  if (!selectedStyle) return "请选择风格";
  return "";
}

function runImg2img() {
  return runFlow({
    url: "/api/img2img",
    buildFd: buildImg2imgFd,
    validate: validateImg2img,
    runningMsg: "正在重绘（" + $("imgN").value + " 张），约需 30~90 秒…",
    statusId: "statusImg",
    btnIds: ["goImg"],
    render(data, el) {
      const imgs = Array.isArray(data.images) ? data.images : [];
      const wrap = $("previewImgs");
      if (!imgs.length) { setStatusEl(el, "未返回图片", true); return; }
      wrap.innerHTML = imgs
        .map(
          (u, i) =>
            `<div class="preview"><img src="${u}" alt="结果${i + 1}">` +
            `<div class="actions"><a class="btn" href="${u}" download="edited_${i + 1}.png">下载第 ${i + 1} 张</a></div></div>`
        )
        .join("");
      $("resultImg").classList.remove("hidden");
      setStatusEl(
        el,
        data.note
          ? data.note
          : "生成完成，" + imgs.length + " 张，风格 " + (data.style || selectedStyle) + "，模型 " + (data.used_model || "")
      );
    },
  });
}

$("goImg").addEventListener("click", runImg2img);
