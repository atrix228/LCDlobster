import * as net from "net";
import { config } from "./config";
import pino from "pino";

const logger = pino({ name: "ipc" });

type StatePayload =
  | { state: "idle" }
  | { state: "thinking" }
  | { state: "responding" }
  | { state: "listening" }
  | { state: "working" }
  | { state: "building" }
  | { state: "error"; message?: string }
  | { state: "qr"; qr_data: string }
  | { state: "network"; ip: string; ssid: string; hostname: string }
  | { connectivity: "connected" | "disconnected" }
  | { provider: string };

const RECONNECT_DELAY_MS = 5000;
const SOCKET_PATH = config.display.socket_path;

let socket: net.Socket | null = null;
let reconnectTimer: NodeJS.Timeout | null = null;
let isConnecting = false;
let displayEnabled = config.display.enabled;

// Queue messages while disconnected so they aren't silently dropped
const pendingQueue: string[] = [];
const MAX_QUEUE_SIZE = 20;

function clearReconnectTimer(): void {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function scheduleReconnect(): void {
  if (!displayEnabled) return;
  clearReconnectTimer();
  reconnectTimer = setTimeout(() => {
    connect();
  }, RECONNECT_DELAY_MS);
}

function drainQueue(sock: net.Socket): void {
  while (pendingQueue.length > 0) {
    const msg = pendingQueue.shift();
    if (msg) {
      try {
        sock.write(msg);
      } catch {
        // If write fails, put it back and stop draining
        pendingQueue.unshift(msg);
        break;
      }
    }
  }
}

function connect(): void {
  if (!displayEnabled) return;
  if (isConnecting || (socket !== null && !socket.destroyed)) return;

  isConnecting = true;

  const sock = net.createConnection({ path: SOCKET_PATH });

  sock.on("connect", () => {
    isConnecting = false;
    socket = sock;
    logger.debug("IPC connected to display socket");
    drainQueue(sock);
  });

  sock.on("error", (err: NodeJS.ErrnoException) => {
    isConnecting = false;
    socket = null;

    if (err.code === "ENOENT" || err.code === "ECONNREFUSED") {
      // Display service not running — silent retry
      logger.debug({ code: err.code }, "Display socket unavailable, will retry");
    } else {
      logger.warn({ err: err.message, code: err.code }, "IPC socket error");
    }

    sock.destroy();
    scheduleReconnect();
  });

  sock.on("close", () => {
    isConnecting = false;
    socket = null;
    logger.debug("IPC socket closed, scheduling reconnect");
    scheduleReconnect();
  });

  sock.on("end", () => {
    socket = null;
    scheduleReconnect();
  });
}

export function initIpc(): void {
  if (!displayEnabled) {
    logger.info("Display IPC disabled in config");
    return;
  }
  connect();
}

export function sendState(state: StatePayload): void {
  if (!displayEnabled) return;

  const payload = JSON.stringify(state) + "\n";

  if (socket !== null && !socket.destroyed) {
    try {
      socket.write(payload);
    } catch (err) {
      logger.debug({ err }, "Failed to write to IPC socket");
      socket = null;
      scheduleReconnect();
      // Enqueue for retry
      if (pendingQueue.length < MAX_QUEUE_SIZE) {
        pendingQueue.push(payload);
      }
    }
  } else {
    // Not connected — enqueue
    if (pendingQueue.length < MAX_QUEUE_SIZE) {
      pendingQueue.push(payload);
    }
    // Trigger a connection attempt if none is pending
    if (!isConnecting && reconnectTimer === null) {
      connect();
    }
  }
}

export function closeIpc(): void {
  displayEnabled = false;
  clearReconnectTimer();
  if (socket) {
    socket.destroy();
    socket = null;
  }
}
