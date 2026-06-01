# 第三方资源说明 (NOTICE)

本插件的桌面渲染部分复用了以下第三方资源：

## EchoBot (MIT License)
- 来源：https://github.com/KdaiP/EchoBot
- 复用内容：
  - `desktop/vendor/pixi.min.js`、`desktop/vendor/live2dcubismcore.min.js`、`desktop/vendor/cubism4.min.js`
  - `desktop/renderer.js` 的 Live2D 加载 / 口型同步逻辑（移植并精简自 EchoBot 的
    `web/features/live2d/model.js`、`scene.js` 与 `web/features/tts/playback.js`）
  - 内置模型 `desktop/models/hiyori_pro_en/`（EchoBot `builtin_live2d`）
- EchoBot 采用 MIT 协议，版权归 KdaiP 所有。

## Live2D Cubism Core
- `desktop/vendor/live2dcubismcore.min.js` 为 Live2D Cubism SDK Core，使用须遵守
  Live2D 官方授权条款：https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html
  以及 https://www.live2d.com/eula/live2d-open-software-license-agreement_en.html

## Hiyori 模型
- Hiyori 为 Live2D 官方提供的示例模型，使用须遵守 Live2D 免费素材使用条款：
  https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html

如需商用或再分发，请自行确认上述各项授权条款。
