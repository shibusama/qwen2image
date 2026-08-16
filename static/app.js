const $ = (sel) => document.querySelector(sel);

let currentMode = "text";
let currentType = "poster";
let lastDataUrl = "";

// 页面加载时获取后端实际模型配置，动态更新描述文案
(async function loadModelConfig() {
  try {
    const resp = await fetch("/api/models/config");
    const data = await resp.json();
    if (data.ok) {
      document.getElementById("modelSummary").textContent = data.summary_model || "未配置";
      document.getElementById("modelImage").textContent = data.image_model || "未配置";
    }
  } catch {
    // 静默失败，保留 HTML 默认文案
  }
})();

// Tab 切换
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentMode = tab.dataset.mode;
    document.querySelectorAll(".panel").forEach((p) =>
      p.classList.toggle("hidden", p.dataset.panel !== currentMode)
    );
  });
});

// 上传文件后显示文件名
$("#file").addEventListener("change", () => {
  const f = $("#file").files[0];
  const label = document.querySelector(".drop span");
  if (f) label.textContent = "已选择：" + f.name;
});

// 类型卡片切换
const typeLabels = { poster: "生成信息图海报", mindmap: "生成思维导图" };
document.querySelectorAll(".type-card").forEach((card) => {
  card.addEventListener("click", () => {
    document.querySelectorAll(".type-card").forEach((c) => c.classList.remove("active"));
    card.classList.add("active");
    currentType = card.dataset.type;
    $("#go").textContent = typeLabels[currentType] || "生成";
  });
});

function setStatus(text, isError) {
  const el = $("#status");
  el.textContent = text;
  el.className = "status" + (isError ? " error" : "");
}

function buildFormData() {
  const fd = new FormData();
  fd.append("mode", currentMode);
  fd.append("size", $("#size").value);
  fd.append("style", $("#style").value);
  fd.append("type", currentType);
  if (currentMode === "file") {
    const f = $("#file").files[0];
    if (f) fd.append("file", f);
  } else if (currentMode === "url") {
    fd.append("url", $("#url").value.trim());
  } else {
    fd.append("content", $("#content").value);
  }
  return fd;
}

function validate(fd) {
  if (currentMode === "file" && !$("#file").files[0]) return "请选择要上传的文件";
  if (currentMode === "url" && !fd.get("url")) return "请输入要抓取的链接";
  if (currentMode === "text" && !fd.get("content").trim()) return "请粘贴要转换的文本";
  return "";
}

async function runGenerate() {
  const fd = buildFormData();
  const err = validate(fd);
  if (err) {
    setStatus(err, true);
    return;
  }
  $("#go").disabled = true;
  $("#again").disabled = true;
  setStatus("正在提炼并生成，约需 30~60 秒…");
  try {
    const resp = await fetch("/api/generate", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      setStatus(data.detail || "生成失败", true);
      return;
    }
    lastDataUrl = data.image_base64;
    $("#preview").src = lastDataUrl;
    $("#download").href = lastDataUrl;
    $("#download").setAttribute("download", "output.png");
    $("#download").textContent = "下载图片";
    $("#result").classList.remove("hidden");
    $("#again").classList.remove("hidden");
    setStatus("生成完成");
  } catch (e) {
    setStatus("网络错误：" + e.message, true);
  } finally {
    $("#go").disabled = false;
    $("#again").disabled = false;
  }
}

$("#go").addEventListener("click", runGenerate);
$("#again").addEventListener("click", runGenerate);
