import { emitEventBus, onEventBus } from "./eventBus";

let wsClient = null;
let reconnectTimer = null;
let reconnectDelayMs = 1000;
let started = false;
let removeSendListener = null;

function websocketUrl() {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/ws/events`;
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, reconnectDelayMs);
  reconnectDelayMs = Math.min(10000, reconnectDelayMs * 2);
}

function sendRaw(payload) {
  if (!wsClient || wsClient.readyState !== WebSocket.OPEN) return false;
  try {
    wsClient.send(JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

function connect() {
  if (!started) return;
  if (wsClient) {
    wsClient.onopen = null;
    wsClient.onmessage = null;
    wsClient.onclose = null;
    wsClient.onerror = null;
    wsClient.close();
  }
  wsClient = new WebSocket(websocketUrl());
  wsClient.onopen = () => {
    reconnectDelayMs = 1000;
    emitEventBus("ws:open", null);
  };
  wsClient.onmessage = (event) => {
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch {
      emitEventBus("ws:parse-error", event.data);
      return;
    }
    emitEventBus("ws:message", payload);
    if (payload?.type === "snapshot") {
      emitEventBus("ws:snapshot", payload);
    }
  };
  wsClient.onerror = () => {
    emitEventBus("ws:error", null);
    try {
      wsClient?.close();
    } catch {
      // Ignore close errors on broken websocket state.
    }
  };
  wsClient.onclose = () => {
    emitEventBus("ws:close", null);
    scheduleReconnect();
  };
}

export function startWebsocketBus() {
  if (started) return;
  started = true;
  removeSendListener = onEventBus("ws:send", (payload) => {
    sendRaw(payload);
  });
  connect();
}

export function stopWebsocketBus() {
  started = false;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (removeSendListener) {
    removeSendListener();
    removeSendListener = null;
  }
  if (wsClient) {
    wsClient.onopen = null;
    wsClient.onmessage = null;
    wsClient.onclose = null;
    wsClient.onerror = null;
    wsClient.close();
    wsClient = null;
  }
}

export function sendWebsocketEvent(payload) {
  return sendRaw(payload);
}
