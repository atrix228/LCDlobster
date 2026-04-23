import path from "path";
import * as fs from "fs";
import qrcode from "qrcode-terminal";
import pino from "pino";
import {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  WASocket,
  BaileysEventMap,
  AuthenticationState,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import { config } from "../config";
import { sendState } from "../ipc";
import { processMessage } from "../conversation";

const logger = pino({ name: "whatsapp-channel" });

// Status broadcast JID — messages to/from this should be skipped
const STATUS_BROADCAST_JID = "status@broadcast";

let waSocket: WASocket | null = null;

async function connectWhatsApp(
  authState: AuthenticationState,
  saveCreds: () => Promise<void>
): Promise<void> {
  const { version } = await fetchLatestBaileysVersion();
  logger.info({ version }, "Using Baileys WA version");

  const sock = makeWASocket({
    version,
    auth: authState,
    printQRInTerminal: false, // We handle QR ourselves
    logger: pino({ name: "baileys", level: "silent" }) as Parameters<
      typeof makeWASocket
    >[0]["logger"],
    connectTimeoutMs: 60000,
    keepAliveIntervalMs: 25000,
    retryRequestDelayMs: 2000,
  });

  waSocket = sock;

  sock.ev.on(
    "connection.update",
    async (update: BaileysEventMap["connection.update"]) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        logger.info("QR code received — displaying on LCD and terminal");
        qrcode.generate(qr, { small: true });
        sendState({ state: "qr", qr_data: qr });
      }

      if (connection === "close") {
        waSocket = null;
        const reason = (lastDisconnect?.error as Boom)?.output?.statusCode;
        const loggedOut = reason === DisconnectReason.loggedOut;

        logger.warn({ reason, loggedOut }, "WhatsApp connection closed");
        sendState({ connectivity: "disconnected" });

        if (!loggedOut) {
          logger.info("Reconnecting to WhatsApp...");
          // Brief delay before reconnect to avoid hammering the server
          setTimeout(() => {
            connectWhatsApp(authState, saveCreds).catch((err: unknown) => {
              logger.error({ err }, "Failed to reconnect WhatsApp");
            });
          }, 5000);
        } else {
          logger.error("WhatsApp logged out — delete session folder and restart to re-authenticate");
        }
      } else if (connection === "open") {
        logger.info("WhatsApp connected");
        sendState({ connectivity: "connected" });
        sendState({ state: "idle" });
      } else if (connection === "connecting") {
        logger.info("WhatsApp connecting...");
      }
    }
  );

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on(
    "messages.upsert",
    async ({ messages, type }: BaileysEventMap["messages.upsert"]) => {
      if (type !== "notify") return;

      for (const msg of messages) {
        // Skip messages sent by this bot
        if (msg.key.fromMe) continue;

        // Skip status broadcasts
        const remoteJid = msg.key.remoteJid;
        if (!remoteJid || remoteJid === STATUS_BROADCAST_JID) continue;

        // Extract text content
        const text =
          msg.message?.conversation ??
          msg.message?.extendedTextMessage?.text ??
          msg.message?.ephemeralMessage?.message?.conversation ??
          msg.message?.ephemeralMessage?.message?.extendedTextMessage?.text;

        if (typeof text !== "string" || text.trim().length === 0) continue;

        const chatId = remoteJid;

        sendState({ state: "listening" });
        logger.info({ chatId }, "Received WhatsApp message");

        try {
          const responseText = await processMessage("whatsapp", chatId, text.trim());

          await sock.sendMessage(chatId, { text: responseText });
          logger.info({ chatId }, "Sent WhatsApp reply");
        } catch (err: unknown) {
          const errMsg = err instanceof Error ? err.message : String(err);
          logger.error({ chatId, err: errMsg }, "Error handling WhatsApp message");

          try {
            await sock.sendMessage(chatId, {
              text: "Sorry, something went wrong. Please try again.",
            });
          } catch {
            // If we can't even send the error message, just log it
            logger.error({ chatId }, "Failed to send error reply");
          }
        }
      }
    }
  );
}

export async function startWhatsAppChannel(): Promise<void> {
  if (!config.channels.whatsapp.enabled) {
    logger.info("WhatsApp channel disabled in config");
    return;
  }

  const sessionPath = path.resolve(process.cwd(), config.channels.whatsapp.session_path);

  if (!fs.existsSync(sessionPath)) {
    fs.mkdirSync(sessionPath, { recursive: true });
    logger.info({ sessionPath }, "Created WhatsApp session directory");
  }

  logger.info({ sessionPath }, "Starting WhatsApp channel");

  const { state, saveCreds } = await useMultiFileAuthState(sessionPath);

  await connectWhatsApp(state, saveCreds);
}
