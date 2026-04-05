# Host Actions Bridge

## 目标

前端聊天时间线中的 `file_ref`、`command_ref`、`preview`、`url` artifact 不直接依赖浏览器行为，
而是统一通过宿主动作层触发。这样在浏览器环境下可以降级为 `window.open / clipboard`，
在 IDE 宿主环境下可以切换为“打开文件并定位行号”“跳转命令记录”“内嵌预览”等动作。

## 支持的动作

- `openUrl`
- `openFile`
- `openCommand`
- `copyText`

## 接入方式一：全局对象

宿主在页面初始化后注入：

```ts
window.__AEGIS_HOST_ACTIONS__ = {
  openUrl: async ({ url, kind }) => {
    console.log("openUrl", url, kind);
    return true;
  },
  openFile: async ({ path, lineStart, lineEnd }) => {
    console.log("openFile", path, lineStart, lineEnd);
    return true;
  },
  openCommand: async ({ commandId, terminalId }) => {
    console.log("openCommand", commandId, terminalId);
    return true;
  },
  copyText: async ({ text }) => {
    await navigator.clipboard.writeText(text);
    return true;
  },
};
```

返回 `true` 表示宿主已处理，前端不会走浏览器降级逻辑。

## 接入方式二：事件监听

宿主如果不方便注入全局对象，也可以监听浏览器事件：

```ts
window.addEventListener("aegis:host-action", (event) => {
  const customEvent = event as CustomEvent;
  const request = customEvent.detail;

  if (request.action === "openFile") {
    console.log("open file in host", request.payload);
    customEvent.preventDefault();
  }
});
```

宿主处理成功后调用 `preventDefault()`，前端会视为该动作已被宿主接管。

## 当前浏览器降级行为

- `openUrl`: `window.open`
- `openFile`: `file:///...#Lx-Ly`
- `openCommand`: 默认不处理，返回给调用方，由 UI 走复制
- `copyText`: `navigator.clipboard.writeText`

## 推荐宿主实现

- `openUrl`: 在外部浏览器或内嵌 webview 打开
- `openFile`: 在 IDE 中打开文件并定位行号
- `openCommand`: 跳转到终端历史或命令详情面板
- `copyText`: 统一走宿主剪贴板接口

