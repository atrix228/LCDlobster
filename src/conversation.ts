import pino from "pino";
import { config } from "./config";
import { addMessage, getHistory } from "./db";
import { sendState } from "./ipc";
import { router } from "./providers/index";

const logger = pino({ name: "conversation" });

export async function processMessage(
  channel: string,
  chatId: string,
  userMessage: string
): Promise<string> {
  logger.info({ channel, chatId }, "Processing message");

  sendState({ state: "thinking" });

  try {
    // Persist the incoming user message
    addMessage(channel, chatId, "user", userMessage);

    // Retrieve conversation history
    const history = getHistory(channel, chatId, config.db.max_history);

    // Call the provider router
    const response = await router.chat(history, config.bot.system_prompt);

    sendState({ state: "responding" });
    sendState({ provider: `${response.provider} / ${response.model}` });

    // Persist the assistant response
    addMessage(channel, chatId, "assistant", response.content);

    logger.info(
      { channel, chatId, provider: response.provider, model: response.model },
      "Response generated"
    );

    sendState({ state: "idle" });

    return response.content;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    logger.error({ channel, chatId, err: message }, "Failed to process message");

    sendState({ state: "error", message });

    // Return a user-facing error string rather than throwing so channels can reply
    return "Sorry, I ran into a problem and couldn't generate a response. Please try again.";
  }
}
