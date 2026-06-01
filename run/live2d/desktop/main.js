// Electron 主进程：创建透明、无边框、置顶的桌宠窗口
const { app, BrowserWindow, ipcMain, screen } = require("electron");
const fs = require("fs");
const path = require("path");

function readRuntimeConfig() {
  const defaults = {
    model_url: null,
    bridge: { host: "127.0.0.1", port: 7765 },
    chat: { enable: true },
    window: {
      width: 420,
      height: 640,
      scale: 0.18,
      always_on_top: true,
      x: null,
      y: null,
    },
  };
  try {
    const raw = fs.readFileSync(path.join(__dirname, "runtime_config.json"), "utf-8");
    const parsed = JSON.parse(raw);
    return {
      ...defaults,
      ...parsed,
      bridge: { ...defaults.bridge, ...(parsed.bridge || {}) },
      chat: { ...defaults.chat, ...(parsed.chat || {}) },
      window: { ...defaults.window, ...(parsed.window || {}) },
    };
  } catch (err) {
    console.warn("[live2d] runtime_config.json 读取失败，使用默认配置:", err.message);
    return defaults;
  }
}

let mainWindow = null;
const runtimeConfig = readRuntimeConfig();

// 桌宠窗口的固定逻辑尺寸。透明无边框窗口在 Windows 上被 setPosition 连续移动时，
// 偶发会让窗口宽/高逐像素漂移变大（用户观察到的“拖动模型时对话框/输入条越来越长”）。
// 这里把尺寸视为不可变量：移动只改坐标、不改尺寸；并监听 resize 把任何意外的尺寸变化拨回。
const FIXED_SIZE = { width: runtimeConfig.window.width, height: runtimeConfig.window.height };

// 命令行单实例锁，避免多次 /live2d on 拉起多个窗口
const gotSingleLock = app.requestSingleInstanceLock();
if (!gotSingleLock) {
  app.quit();
}

function createWindow() {
  const win = runtimeConfig.window;
  const display = screen.getPrimaryDisplay();
  const work = display.workAreaSize;

  // 默认定位到屏幕右下角，留出 24px 边距
  const posX = Number.isFinite(win.x) ? win.x : Math.max(0, work.width - win.width - 24);
  const posY = Number.isFinite(win.y) ? win.y : Math.max(0, work.height - win.height - 24);

  mainWindow = new BrowserWindow({
    width: win.width,
    height: win.height,
    x: posX,
    y: posY,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: Boolean(win.always_on_top),
    hasShadow: false,
    fullscreenable: false,
    maximizable: false,
    minimizable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
      // 本地桌宠：允许加载任意目录下的模型(file://)与回复音频/图片，便于自定义模型文件夹
      webSecurity: false,
    },
  });

  if (win.always_on_top) {
    // screen-saver 层级可覆盖大多数全屏应用
    mainWindow.setAlwaysOnTop(true, "screen-saver");
  }

  // 默认整窗鼠标穿透（透明区域点击直达桌面）；forward:true 让渲染层仍能收到
  // mousemove，以便在指针移到模型/UI 上时再切回可交互。
  mainWindow.setIgnoreMouseEvents(true, { forward: true });

  mainWindow.loadFile(path.join(__dirname, "index.html"));

  // 尺寸守卫：任何让窗口尺寸偏离固定值的事件（移动漂移 / DPI 变化等）都立即拨回，
  // 从根上消除“拖动时窗口变宽 → 底部输入条/对话框越来越长”。判等避免无限触发。
  mainWindow.on("resize", () => {
    if (!mainWindow) return;
    const [w, h] = mainWindow.getSize();
    if (w !== FIXED_SIZE.width || h !== FIXED_SIZE.height) {
      mainWindow.setSize(FIXED_SIZE.width, FIXED_SIZE.height);
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// 渲染层把运行时配置取走（模型、bridge 端口、缩放等）
ipcMain.handle("live2d:get-config", () => runtimeConfig);

// 拖拽模型 → 移动窗口。用 setBounds 一次性给定“新坐标 + 固定尺寸”，
// 避免 setPosition 在透明窗口上引发的尺寸漂移（拖动越久窗口越宽）。
ipcMain.on("live2d:move-by", (_event, dx, dy) => {
  if (!mainWindow) return;
  const b = mainWindow.getBounds();
  mainWindow.setBounds({
    x: Math.round(b.x + dx),
    y: Math.round(b.y + dy),
    width: FIXED_SIZE.width,
    height: FIXED_SIZE.height,
  });
});

// 鼠标穿透开关：renderer 根据指针是否在模型/UI 上来切换
ipcMain.on("live2d:set-ignore", (_event, ignore) => {
  if (!mainWindow) return;
  mainWindow.setIgnoreMouseEvents(Boolean(ignore), { forward: true });
});

ipcMain.on("live2d:quit", () => {
  app.quit();
});

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  app.quit();
});
