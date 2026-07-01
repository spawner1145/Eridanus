// 预加载脚本：通过 contextBridge 安全暴露受限能力给渲染层
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  // 取运行时配置（模型、bridge、window）
  getConfig: () => ipcRenderer.invoke("live2d:get-config"),
  // 拖拽模型时移动整个窗口
  moveBy: (dx, dy) => ipcRenderer.send("live2d:move-by", dx, dy),
  // 鼠标穿透开关（true=穿透，false=可交互）
  setIgnoreMouse: (ignore) => ipcRenderer.send("live2d:set-ignore", ignore),
  // 请求退出
  quit: () => ipcRenderer.send("live2d:quit"),
  // 把字节交回主进程，弹原生保存对话框另存（聊天里的图片/文件下载）
  saveFile: (name, bytes) => ipcRenderer.invoke("live2d:save-bytes", name, bytes),
  // 在模型上右键时弹出原生菜单（含「关闭桌宠」）
  showContextMenu: () => ipcRenderer.send("live2d:context-menu"),
});
