import express, { Request, Response, NextFunction } from "express";
import pino from "pino";
import { config } from "../config";
import { clearHistory } from "../db";
import { sendState } from "../ipc";
import { processMessage } from "../conversation";
import { router } from "../providers/index";

const logger = pino({ name: "http-channel" });

interface ChatRequestBody {
  chatId?: unknown;
  message?: unknown;
}

export function startHttpChannel(): void {
  if (!config.channels.http.enabled) {
    logger.info("HTTP channel disabled in config");
    return;
  }

  const app = express();
  app.use(express.json());

  // POST /chat — send a message and get a response
  app.post(
    "/chat",
    (req: Request<Record<string, never>, unknown, ChatRequestBody>, res: Response): void => {
      const { chatId, message } = req.body;

      if (typeof chatId !== "string" || chatId.trim().length === 0) {
        res.status(400).json({ error: "chatId must be a non-empty string" });
        return;
      }

      if (typeof message !== "string" || message.trim().length === 0) {
        res.status(400).json({ error: "message must be a non-empty string" });
        return;
      }

      const normalizedChatId = chatId.trim();
      const normalizedMessage = message.trim();

      sendState({ state: "listening" });
      logger.info({ chatId: normalizedChatId }, "Received HTTP chat message");

      processMessage("http", normalizedChatId, normalizedMessage)
        .then((responseText) => {
          res.json({
            response: responseText,
            provider: router.getCurrentProvider(),
          });
        })
        .catch((err: unknown) => {
          const errMsg = err instanceof Error ? err.message : String(err);
          logger.error({ err: errMsg }, "Unhandled error in /chat handler");
          res.status(500).json({ error: "Internal server error" });
        });
    }
  );

  // GET /status — health check
  app.get("/status", (_req: Request, res: Response): void => {
    res.json({
      status: "ok",
      provider: router.getCurrentProvider(),
      bot: config.bot.name,
    });
  });

  // POST /clear/:chatId — clear conversation history for a chat
  app.post("/clear/:chatId", (req: Request<{ chatId: string }>, res: Response): void => {
    const { chatId } = req.params;

    if (!chatId || chatId.trim().length === 0) {
      res.status(400).json({ error: "chatId param is required" });
      return;
    }

    try {
      clearHistory("http", chatId.trim());
      logger.info({ chatId }, "Cleared HTTP conversation history");
      res.json({ cleared: true, chatId: chatId.trim() });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      logger.error({ err: errMsg, chatId }, "Failed to clear history");
      res.status(500).json({ error: "Failed to clear history" });
    }
  });

  // Generic error handler
  app.use((err: Error, _req: Request, res: Response, _next: NextFunction): void => {
    logger.error({ err: err.message }, "Unhandled Express error");
    res.status(500).json({ error: "Internal server error" });
  });

  const { port, host } = config.channels.http;

  app.listen(port, host, () => {
    logger.info({ host, port }, "HTTP channel listening");
  });
}
