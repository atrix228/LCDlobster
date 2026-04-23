import { execFile } from "child_process";
import * as os from "os";
import pino from "pino";
import { config } from "./config";
import { initDb } from "./db";
import { initIpc, sendState, closeIpc } from "./ipc";
import { startHttpChannel } from "./channels/http";
import { startWhatsAppChannel } from "./channels/whatsapp";

const logger = pino({
  name: "lcdlobster",
  transport:
    process.env.NODE_ENV !== "production"
      ? { target: "pino-pretty", options: { colorize: true, translateTime: "SYS:standard" } }
      : undefined,
});

// ── Network info ──────────────────────────────────────────────────────────────

function getLocalIp(): string {
  for (const ifaces of Object.values(os.networkInterfaces())) {
    for (const info of ifaces ?? []) {
      if (info.family === "IPv4" && !info.internal) return info.address;
    }
  }
  return "";
}

function getWifiSsid(): Promise<string> {
  return new Promise((resolve) => {
    execFile("iwgetid", ["-r"], { timeout: 3000 }, (err, stdout) => {
      resolve(err ? "" : stdout.trim());
    });
  });
}

// ── Connectivity monitor ──────────────────────────────────────────────────────

const CONNECTIVITY_INTERFACES = ["bt-pan0", "bnep0"];
const CONNECTIVITY_INTERVAL_MS = 30_000;

function checkConnectivity(): void {
  execFile("ip", ["link", "show"], { timeout: 5000 }, (err, stdout) => {
    if (err) {
      logger.debug({ err: err.message }, "ip link show failed");
      return;
    }

    const up = CONNECTIVITY_INTERFACES.some((iface) => {
      // e.g. "2: bt-pan0: <BROADCAST,MULTICAST,UP,LOWER_UP>"
      const re = new RegExp(`:\\s+${iface}:\\s+<[^>]*\\bUP\\b`);
      return re.test(stdout);
    });

    sendState({ connectivity: up ? "connected" : "disconnected" });
  });
}

function startConnectivityMonitor(): void {
  // Run immediately, then on interval
  checkConnectivity();
  setInterval(checkConnectivity, CONNECTIVITY_INTERVAL_MS).unref();
}

// ── Graceful shutdown ─────────────────────────────────────────────────────────

function shutdown(signal: string): void {
  logger.info({ signal }, "Shutting down");
  sendState({ state: "idle" });
  closeIpc();
  // Give IPC a moment to flush, then exit
  setTimeout(() => {
    process.exit(0);
  }, 500);
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));

// ── Bootstrap ─────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  logger.info({ bot: config.bot.name, version: "1.0.0" }, "Starting LCDLobster");

  // 1. Announce startup to display — show network info screen first
  initIpc();
  const [ssid] = await Promise.all([getWifiSsid()]);
  sendState({
    state: "network",
    ip: getLocalIp(),
    ssid,
    hostname: os.hostname(),
  });

  // After 10 s switch to building state while the rest of startup runs
  setTimeout(() => sendState({ state: "building" }), 10_000);

  // 2. Initialise database
  logger.info({ path: config.db.path }, "Initialising database");
  initDb();

  // 3. Start connectivity monitor
  startConnectivityMonitor();

  // 4. Start channels
  if (config.channels.http.enabled) {
    logger.info("Starting HTTP channel");
    startHttpChannel();
  }

  if (config.channels.whatsapp.enabled) {
    logger.info("Starting WhatsApp channel");
    try {
      await startWhatsAppChannel();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      logger.error({ err: message }, "WhatsApp channel failed to start");
      sendState({ state: "error", message: "WhatsApp failed to start" });
      // Non-fatal: continue running with HTTP channel
    }
  }

  // 5. Signal ready
  sendState({ state: "idle" });
  logger.info(
    {
      bot: config.bot.name,
      http: config.channels.http.enabled
        ? `${config.channels.http.host}:${config.channels.http.port}`
        : "disabled",
      whatsapp: config.channels.whatsapp.enabled ? "enabled" : "disabled",
    },
    "LCDLobster ready"
  );
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? err.message : String(err);
  logger.fatal({ err: message }, "Fatal startup error");
  sendState({ state: "error", message });
  process.exit(1);
});
