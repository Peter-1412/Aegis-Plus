export type HostActionBridge = {
  openUrl?: (payload: { url: string; kind?: "url" | "preview" }) => boolean | Promise<boolean>;
  openFile?: (payload: { path: string; lineStart?: number; lineEnd?: number }) => boolean | Promise<boolean>;
  openCommand?: (payload: { commandId: string; terminalId?: string }) => boolean | Promise<boolean>;
  copyText?: (payload: { text: string }) => boolean | Promise<boolean>;
};

export type HostActionRequest =
  | {
      action: "openUrl";
      payload: { url: string; kind?: "url" | "preview" };
    }
  | {
      action: "openFile";
      payload: { path: string; lineStart?: number; lineEnd?: number };
    }
  | {
      action: "openCommand";
      payload: { commandId: string; terminalId?: string };
    }
  | {
      action: "copyText";
      payload: { text: string };
    };

declare global {
  interface Window {
    __AEGIS_HOST_ACTIONS__?: HostActionBridge;
  }
}

function toFileUrl(path: string, lineStart?: number, lineEnd?: number) {
  const normalized = path.replace(/\\/g, "/");
  const prefix = normalized.startsWith("/") ? "" : "/";
  const lineSuffix =
    typeof lineStart === "number"
      ? `#L${lineStart}${typeof lineEnd === "number" ? `-L${lineEnd}` : ""}`
      : "";
  return `file://${prefix}${normalized}${lineSuffix}`;
}

function dispatchHostActionEvent(request: HostActionRequest) {
  const event = new CustomEvent<HostActionRequest>("aegis:host-action", {
    detail: request,
    cancelable: true,
  });
  const handled = window.dispatchEvent(event);
  return handled === false || event.defaultPrevented;
}

async function callBridge<T>(fn: ((payload: T) => boolean | Promise<boolean>) | undefined, payload: T) {
  if (!fn) return false;
  try {
    return Boolean(await fn(payload));
  } catch {
    return false;
  }
}

export function registerHostActions(bridge: HostActionBridge) {
  window.__AEGIS_HOST_ACTIONS__ = bridge;
}

export async function openArtifactUrl(url: string, kind: "url" | "preview" = "url") {
  const payload = { url, kind };
  const handled =
    (await callBridge(window.__AEGIS_HOST_ACTIONS__?.openUrl, payload)) ||
    dispatchHostActionEvent({ action: "openUrl", payload });
  if (!handled) {
    window.open(url, "_blank", "noreferrer");
  }
}

export async function openArtifactFile(path: string, lineStart?: number, lineEnd?: number) {
  const payload = {
    path,
    lineStart,
    lineEnd,
  };
  const handled =
    (await callBridge(window.__AEGIS_HOST_ACTIONS__?.openFile, payload)) ||
    dispatchHostActionEvent({ action: "openFile", payload });
  if (!handled) {
    window.open(toFileUrl(path, lineStart, lineEnd), "_blank", "noreferrer");
  }
}

export async function openArtifactCommand(commandId: string, terminalId?: string) {
  const payload = {
    commandId,
    terminalId,
  };
  return (
    (await callBridge(window.__AEGIS_HOST_ACTIONS__?.openCommand, payload)) ||
    dispatchHostActionEvent({ action: "openCommand", payload })
  );
}

export async function copyArtifactText(text: string) {
  const payload = { text };
  const handled =
    (await callBridge(window.__AEGIS_HOST_ACTIONS__?.copyText, payload)) ||
    dispatchHostActionEvent({ action: "copyText", payload });
  if (!handled) {
    await navigator.clipboard.writeText(text);
  }
}
