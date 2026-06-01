// Live2D 桌宠渲染层
// 移植并精简自 EchoBot (MIT) 的 web/features/live2d/{model,scene}.js 与 tts/playback.js
/* global PIXI */

const canvas = document.getElementById("live2d-canvas");
const bubbleEl = document.getElementById("bubble");
const statusEl = document.getElementById("status");

const state = {
  config: null,
  app: null,
  model: null,
  scale: 0.18,
  // 口型
  currentMouthValue: 0,
  lipSyncIds: ["ParamMouthOpenY"],
  internalModel: null,
  lipSyncHook: null,
  // 拖拽
  dragging: false,
  lastPointer: { x: 0, y: 0 },
  bubbleTimer: 0,
  audioContext: null,
  webuiWs: null,   // 唯一连接：webui 的 /api/ws（与浏览器前端同源）
  history: [],
  ignoringMouse: true, // 与 main.js 初始 setIgnoreMouseEvents(true) 保持一致
};

function setStatus(text) {
  statusEl.textContent = text || "";
  statusEl.style.display = text ? "block" : "none";
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

// ---------- 模型加载 ----------

// 把本地路径/file:// 统一成可被渲染端正确加载的 file:// URL，并对中文等非 ASCII 字符编码
// （data/yumi 等 VTube 模型的 *.exp3.json/*.motion3.json 多为中文文件名，未编码会加载失败）。
function toFileUrl(value) {
  if (!value) return value;
  if (value.startsWith("base64://")) return "data:image/png;base64," + value.slice("base64://".length);
  if (/^https?:\/\//i.test(value) || value.startsWith("data:")) return value;
  let p = value.startsWith("file://") ? value.slice("file://".length) : value;
  p = p.replace(/\\/g, "/");
  if (/^[A-Za-z]:\//.test(p)) p = "/" + p; // Windows 盘符 D:/... -> /D:/...
  if (!p.startsWith("/")) p = "/" + p;
  return "file://" + encodeURI(p);
}

async function loadModel(url) {
  if (!url) {
    setStatus("未配置模型路径（model_path / model）");
    return false;
  }
  setStatus("正在加载 Live2D 模型…");

  try {
    // autoUpdate:false —— pixi-live2d-display 独立打包版不会自动注册 ticker，默认 autoUpdate
    // 会因“无 ticker”而静默不更新，导致模型加载成功却不渲染（空白）。这里关掉自动更新，
    // 由 app 渲染循环手动 model.update()（见 boot 里的 ticker.add），确保稳定渲染。
    const model = await PIXI.live2d.Live2DModel.from(toFileUrl(url), { autoInteract: false, autoUpdate: false });

    disposeModel();
    state.model = model;
    state.app.stage.addChild(model);

    model.anchor.set(0.5, 0.5);
    layoutModel();
    attachLipSyncHook(model);

    bindModelInteractions(model);
    setStatus("");
    return true;
  } catch (err) {
    console.error("[live2d] 模型加载失败:", err);
    setStatus(`模型加载失败：${err && err.message ? err.message : err}`);
    return false;
  }
}

function layoutModel() {
  if (!state.model || !state.app) return;
  state.model.scale.set(state.scale);
  state.model.position.set(
    state.app.renderer.width / 2,
    state.app.renderer.height / 2,
  );
}

function disposeModel() {
  detachLipSyncHook();
  if (state.model) {
    try {
      state.app.stage.removeChild(state.model);
      state.model.destroy({ children: true });
    } catch (err) {
      console.warn("[live2d] 销毁模型失败:", err);
    }
  }
  state.model = null;
}

// ---------- 口型同步 ----------

function attachLipSyncHook(model) {
  detachLipSyncHook();
  const internalModel = model.internalModel;
  if (!internalModel || typeof internalModel.on !== "function") return;

  state.lipSyncHook = function () {
    const coreModel = internalModel.coreModel;
    if (!coreModel || typeof coreModel.setParameterValueById !== "function") return;
    state.lipSyncIds.forEach((id) => {
      try {
        coreModel.setParameterValueById(id, state.currentMouthValue);
      } catch (err) {
        // 某些模型没有该参数，忽略
      }
    });
  };
  internalModel.on("beforeModelUpdate", state.lipSyncHook);
  state.internalModel = internalModel;
}

function detachLipSyncHook() {
  if (state.internalModel && state.lipSyncHook && typeof state.internalModel.off === "function") {
    state.internalModel.off("beforeModelUpdate", state.lipSyncHook);
  }
  state.internalModel = null;
  state.lipSyncHook = null;
}

function smooth(prev, next, factor) {
  return prev + (next - prev) * factor;
}

// 播放音频并用 AnalyserNode 音量驱动口型（移植自 EchoBot playback.js）
async function playAudio(src) {
  try {
    if (!state.audioContext) {
      state.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    const ctx = state.audioContext;
    if (ctx.state === "suspended") await ctx.resume();

    const resp = await fetch(src);
    const arrayBuf = await resp.arrayBuffer();
    const audioBuf = await ctx.decodeAudioData(arrayBuf.slice(0));

    const source = ctx.createBufferSource();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.buffer = audioBuf;
    source.connect(analyser);
    analyser.connect(ctx.destination);

    const data = new Uint8Array(analyser.frequencyBinCount);
    let raf = 0;
    const tick = () => {
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) sum += data[i];
      const avg = sum / data.length / 255; // 0..1
      state.currentMouthValue = smooth(state.currentMouthValue, clamp(avg * 1.8, 0, 1), 0.5);
      raf = window.requestAnimationFrame(tick);
    };

    source.onended = () => {
      window.cancelAnimationFrame(raf);
      state.currentMouthValue = 0;
    };

    source.start(0);
    tick();
  } catch (err) {
    console.error("[live2d] 音频播放失败:", err);
  }
}

// ---------- 气泡 ----------

function _showBubbleEl(durationMs) {
  bubbleEl.classList.add("visible");
  if (state.bubbleTimer) window.clearTimeout(state.bubbleTimer);
  state.bubbleTimer = window.setTimeout(() => {
    bubbleEl.classList.remove("visible");
  }, durationMs);
}

function showBubble(text, durationMs) {
  bubbleEl.textContent = String(text || "");
  const dur = Number.isFinite(durationMs) ? durationMs : Math.max(2500, String(text).length * 180);
  _showBubbleEl(dur);
}

function showBubbleImage(url, durationMs) {
  bubbleEl.textContent = "";
  const img = document.createElement("img");
  img.src = url;
  bubbleEl.appendChild(img);
  _showBubbleEl(Number.isFinite(durationMs) ? durationMs : 5000);
}

// ---------- 交互：拖拽移动窗口 + 滚轮缩放 ----------

function bindModelInteractions(model) {
  model.interactive = true;
  model.cursor = "grab";

  model.on("pointerdown", (event) => {
    state.dragging = true;
    const g = event.data.global;
    state.lastPointer = { x: g.x, y: g.y };
    model.cursor = "grabbing";
  });
}

function bindGlobalInteractions() {
  window.addEventListener("pointermove", (event) => {
    if (!state.dragging) return;
    const dx = event.screenX - (state.lastPointer.screenX ?? event.screenX);
    const dy = event.screenY - (state.lastPointer.screenY ?? event.screenY);
    // 用屏幕坐标增量驱动窗口移动，避免窗口移动后画布坐标漂移
    if (state.lastPointer.screenX != null) {
      window.desktop.moveBy(dx, dy);
    }
    state.lastPointer.screenX = event.screenX;
    state.lastPointer.screenY = event.screenY;
  });

  window.addEventListener("pointerup", () => {
    state.dragging = false;
    state.lastPointer.screenX = null;
    state.lastPointer.screenY = null;
    if (state.model) state.model.cursor = "grab";
  });

  window.addEventListener("wheel", (event) => {
    // 历史面板内滚动不缩放模型
    if (event.target && event.target.closest && event.target.closest("#history-panel, #chat-bar")) return;
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.01 : 0.01;
    state.scale = clamp(state.scale + delta, 0.04, 1.2);
    layoutModel();
  }, { passive: false });

  // 鼠标穿透：移动时实时判断指针是否在模型/UI 上（forward:true 保证穿透时仍收到事件）
  window.addEventListener("mousemove", (event) => {
    updateMouseThrough(event.clientX, event.clientY);
  });
}

// ---------- webui /api/ws：唯一连接，与浏览器前端同源的对话通道 ----------

function connectWebui() {
  const w = state.config.webui || { host: "127.0.0.1", port: 5007 };
  const url = `ws://${w.host || "127.0.0.1"}:${w.port || 5007}/api/ws`;
  let ws;

  const connect = () => {
    ws = new WebSocket(url);
    state.webuiWs = ws;
    ws.onopen = () => {
      console.log("[live2d] 已连接对话后端", url);
    };
    ws.onmessage = (msg) => {
      let frame;
      try {
        frame = JSON.parse(msg.data);
      } catch (err) {
        return;
      }
      handleWebuiFrame(frame);
    };
    ws.onclose = () => {
      window.setTimeout(connect, 2000); // 断线重连，便于 webui/bot 重启
    };
    ws.onerror = () => {
      try { ws.close(); } catch (e) { /* ignore */ }
    };
  };
  connect();
}

// 集线器把每条帧广播给“除发送者外的所有客户端”。等价于 webui 前端 rt()/Ne()：
//   t.message 为数组 → 其它客户端的用户消息（忽略，自己输入已本地入历史）
//   t.message 为 OneBot 动作对象 → 机器人回复，取 params.message 逐段渲染
function handleWebuiFrame(t) {
  if (!t || !t.message) return;
  const m = t.message;
  if (Array.isArray(m)) return;
  const params = m.params || {};
  switch (m.action) {
    case "send_group_msg":
      renderBotSegments(params.message || []);
      break;
    case "send_group_forward_msg":
      for (const node of params.messages || []) {
        const content = node && node.data && node.data.content;
        if (Array.isArray(content)) renderBotSegments(content);
      }
      break;
    case "upload_group_file": {
      const label = "📎 文件" + (params.name ? `：${params.name}` : "");
      showBubble(label);
      addHistory("bot", "text", label);
      break;
    }
    default:
      break;
  }
}

// 逐段渲染机器人回复：文字→气泡+历史(+表情控制)；图片→缩略+历史；语音→播放驱动口型；
// 视频/文件→气泡标签+历史。媒体统一用 file:// 直接加载（桌宠与 bot 同机，webSecurity:false）。
function renderBotSegments(segments) {
  const texts = [];
  for (const seg of segments || []) {
    if (!seg || !seg.type) continue;
    const data = seg.data || {};
    switch (seg.type) {
      case "text":
        if (data.text) texts.push(String(data.text));
        break;
      case "image": {
        const url = toFileUrl(data.file || data.url);
        if (url) {
          showBubbleImage(url);
          addHistory("bot", "image", url);
        }
        break;
      }
      case "record": {
        const url = toFileUrl(data.file || data.url);
        if (url) playAudio(url);
        break;
      }
      case "video": {
        showBubble("🎬 视频");
        addHistory("bot", "text", "🎬 视频");
        break;
      }
      case "file": {
        const label = "📎 文件" + (data.name ? `：${data.name}` : "");
        showBubble(label);
        addHistory("bot", "text", label);
        break;
      }
      default:
        break; // at / reply / face 等忽略
    }
  }
  if (texts.length) {
    const joined = texts.join("\n");
    showBubble(joined);
    addHistory("bot", "text", joined);
    controlExpression(joined);
  }
}

// ---------- 表情/动作自动控制（渲染端调用快速模型，自适应当前模型可用项） ----------

function availableExprMotion() {
  // 优先从已加载模型读取真实可用项，回退 runtime_config 下发的清单
  let exprs = [];
  let motions = [];
  try {
    const settings = state.model && state.model.internalModel && state.model.internalModel.settings;
    if (settings) {
      const exprDefs = settings.expressions || (settings.FileReferences && settings.FileReferences.Expressions);
      if (Array.isArray(exprDefs)) exprs = exprDefs.map((e) => e.Name || e.name).filter(Boolean);
      const motionDefs = settings.motions || (settings.FileReferences && settings.FileReferences.Motions);
      if (motionDefs) motions = Object.keys(motionDefs);
    }
  } catch (e) { /* ignore */ }
  if (!exprs.length) exprs = state.config.expr_names || [];
  if (!motions.length) motions = state.config.motion_names || [];
  return { exprs, motions };
}

async function controlExpression(text) {
  const cfg = state.config.expression || {};
  if (cfg.enable === false || !cfg.base_url) return;
  const { exprs, motions } = availableExprMotion();
  if (!exprs.length && !motions.length) return;
  const t = (text || "").trim();
  if (!t) return;

  let raw;
  try {
    raw = await fastLLM(cfg, buildExprPrompt(t, exprs, motions));
  } catch (e) {
    return; // 表情控制失败不影响对话
  }
  if (!raw) return;
  const { expression, motion } = parseExprJson(raw, exprs, motions);
  if (expression && state.model) {
    try { state.model.expression(expression); } catch (e) { /* ignore */ }
  }
  if (motion && state.model) {
    try { state.model.motion(motion, undefined, PIXI.live2d.MotionPriority?.NORMAL ?? 2); } catch (e) { /* ignore */ }
  }
}

function buildExprPrompt(text, exprs, motions) {
  const parts = [
    "你是 Live2D 形象的表情/动作控制器。根据下面这句【角色台词】的情绪和语义，",
    "从“可用表情”和“可用动作”中各挑选最贴合的一个（不合适就留空）。",
    "只输出一行 JSON，不要解释：{\"expression\": \"名称或空字符串\", \"motion\": \"名称或空字符串\"}",
    "名称必须从清单里精确选取，不要自创、不要翻译。",
  ];
  if (exprs.length) parts.push("可用表情：" + exprs.join("、"));
  if (motions.length) parts.push("可用动作：" + motions.join("、"));
  parts.push("【角色台词】" + text);
  return parts.join("\n");
}

function parseExprJson(raw, exprs, motions) {
  const m = String(raw).match(/\{[^{}]*\}/);
  if (!m) return {};
  let obj;
  try {
    obj = JSON.parse(m[0]);
  } catch (e) {
    return {};
  }
  let expression = String(obj.expression || "").trim();
  let motion = String(obj.motion || "").trim();
  if (exprs.indexOf(expression) < 0) expression = "";
  if (motions.indexOf(motion) < 0) motion = "";
  return { expression, motion };
}

async function fastLLM(cfg, prompt) {
  const url = cfg.base_url.replace(/\/+$/, "") + "/chat/completions";
  const headers = { "Content-Type": "application/json" };
  if (cfg.api_key) headers.Authorization = "Bearer " + cfg.api_key;
  const body = {
    model: cfg.model || "gpt-4o-mini",
    messages: [{ role: "user", content: prompt }],
    temperature: 0.3,
    max_tokens: 60,
    stream: false,
  };
  const resp = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  const data = await resp.json();
  try {
    return data.choices[0].message.content;
  } catch (e) {
    return null;
  }
}

// ---------- 聊天输入条 ----------

function setupChatUI() {
  const chatEnabled = !state.config.chat || state.config.chat.enable !== false;
  const bar = document.getElementById("chat-bar");
  if (!chatEnabled) {
    if (bar) bar.style.display = "none";
    return;
  }
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");

  const sendChat = () => {
    const text = (input.value || "").trim();
    if (!text) return;
    const ws = state.webuiWs;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      showBubble("未连接到对话后端(/api/ws)，无法发送。");
      return;
    }
    // 与 webui 前端完全一致：首元素携带 msg_id，随后自动注入 @机器人 段（qq=1000000 命中
    // mai_reply 的“被@必回”），再附文本段。
    const payload = [
      { msg_id: Date.now() },
      { type: "at", data: { qq: "1000000", name: "Eridanus" } },
      { type: "text", data: { text } },
    ];
    ws.send(JSON.stringify(payload));
    addHistory("user", "text", text);
    input.value = "";
  };

  sendBtn.addEventListener("click", sendChat);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });

  // 历史面板开关
  const panel = document.getElementById("history-panel");
  document.getElementById("history-toggle").addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) renderHistory();
  });
  document.getElementById("history-close").addEventListener("click", () => panel.classList.remove("open"));
  document.getElementById("history-clear").addEventListener("click", () => {
    state.history = [];
    saveHistory();
    renderHistory();
  });
}

// ---------- 历史对话（localStorage 持久化） ----------

const HISTORY_KEY = "live2d_history";
const HISTORY_MAX = 300;

function loadHistory() {
  try {
    state.history = JSON.parse(window.localStorage.getItem(HISTORY_KEY) || "[]");
  } catch (e) {
    state.history = [];
  }
}

function saveHistory() {
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history.slice(-HISTORY_MAX)));
  } catch (e) { /* ignore */ }
}

function addHistory(role, kind, content) {
  if (!state.history) state.history = [];
  state.history.push({ role, kind, content, ts: Date.now() });
  if (state.history.length > HISTORY_MAX) state.history = state.history.slice(-HISTORY_MAX);
  saveHistory();
  const panel = document.getElementById("history-panel");
  if (panel && panel.classList.contains("open")) renderHistory();
}

function renderHistory() {
  const log = document.getElementById("history-log");
  if (!log) return;
  log.innerHTML = "";
  for (const item of state.history || []) {
    const line = document.createElement("div");
    line.className = `h-line ${item.role === "user" ? "h-user" : "h-bot"}`;
    if (item.kind === "image") {
      const img = document.createElement("img");
      img.src = item.content;
      line.appendChild(img);
    } else {
      line.textContent = item.content;
    }
    log.appendChild(line);
  }
  log.scrollTop = log.scrollHeight;
}

// ---------- 鼠标穿透：仅模型与 UI 可交互，透明区域点击直达桌面 ----------

function isInteractiveAt(clientX, clientY) {
  if (state.dragging) return true;
  // 命中 UI（输入条 / 历史面板）
  const el = document.elementFromPoint(clientX, clientY);
  if (el && el.closest && el.closest("#chat-bar, #history-panel")) return true;
  // 命中模型包围盒
  if (state.model) {
    try {
      const b = state.model.getBounds();
      const pad = 6;
      if (clientX >= b.x - pad && clientX <= b.x + b.width + pad &&
          clientY >= b.y - pad && clientY <= b.y + b.height + pad) {
        return true;
      }
    } catch (e) { /* ignore */ }
  }
  return false;
}

function updateMouseThrough(clientX, clientY) {
  const interactive = isInteractiveAt(clientX, clientY);
  const ignore = !interactive;
  if (ignore !== state.ignoringMouse) {
    state.ignoringMouse = ignore;
    window.desktop.setIgnoreMouse(ignore);
  }
}

// ---------- 启动 ----------

async function boot() {
  state.config = await window.desktop.getConfig();
  state.scale = (state.config.window && state.config.window.scale) || 0.18;
  if (Array.isArray(state.config.lip_sync_parameter_ids) && state.config.lip_sync_parameter_ids.length) {
    state.lipSyncIds = state.config.lip_sync_parameter_ids;
  }

  state.app = new PIXI.Application({
    view: canvas,
    backgroundAlpha: 0,
    antialias: true,
    resizeTo: window,
    autoDensity: true,
    resolution: window.devicePixelRatio || 1,
  });

  // 每帧手动驱动 Live2D 更新（模型以 autoUpdate:false 加载）。app 渲染循环本就在跑，
  // 在同一循环里 update，避免依赖 Ticker.shared 是否启动，是“加载成功却空白”的根因修复。
  state.app.ticker.add(() => {
    if (state.model) {
      try { state.model.update(state.app.ticker.deltaMS); } catch (e) { /* ignore */ }
    }
  });

  loadHistory();
  bindGlobalInteractions();
  setupChatUI();
  window.addEventListener("resize", layoutModel);

  await loadModel(state.config.model_url);
  connectWebui();    // 唯一连接：webui 的 /api/ws（对话 + 表情/动作由回复内容在本地驱动）
}

boot().catch((err) => {
  console.error("[live2d] 启动失败:", err);
  setStatus(`启动失败：${err && err.message ? err.message : err}`);
});
