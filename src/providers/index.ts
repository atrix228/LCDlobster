import pino from "pino";
import { config } from "../config";
import { sendState } from "../ipc";
import { Message, Provider, ProviderResponse } from "./types";
import { MiniMaxProvider } from "./minimax";
import { OpenRouterProvider } from "./openrouter";
import { AnthropicProvider } from "./anthropic";

const logger = pino({ name: "provider-router" });

const PROVIDER_MAP: Record<string, Provider> = {
  minimax: new MiniMaxProvider(),
  openrouter: new OpenRouterProvider(),
  anthropic: new AnthropicProvider(),
};

class ProviderRouter {
  private providers: Provider[];
  private currentProvider: string = "none";

  constructor() {
    // Build the ordered list from config priority, keeping only known providers
    this.providers = config.providers.priority
      .map((name) => PROVIDER_MAP[name])
      .filter((p): p is Provider => p !== undefined);

    if (this.providers.length === 0) {
      throw new Error("No valid providers configured in providers.priority");
    }

    logger.info(
      { priority: this.providers.map((p) => p.name) },
      "Provider router initialized"
    );
  }

  async chat(messages: Message[], systemPrompt: string): Promise<ProviderResponse> {
    const available = this.providers.filter((p) => p.isAvailable());

    if (available.length === 0) {
      sendState({ state: "error", message: "No providers available" });
      throw new Error("No providers have a valid API key configured");
    }

    const errors: string[] = [];

    for (const provider of available) {
      try {
        logger.debug({ provider: provider.name }, "Attempting provider");
        const response = await provider.chat(messages, systemPrompt);
        this.currentProvider = provider.name;
        logger.debug({ provider: provider.name }, "Provider succeeded");
        return response;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        logger.warn({ provider: provider.name, err: message }, "Provider failed, trying next");
        errors.push(`${provider.name}: ${message}`);
      }
    }

    const combinedError = `All providers failed:\n${errors.join("\n")}`;
    sendState({ state: "error", message: "All AI providers failed" });
    this.currentProvider = "none";
    throw new Error(combinedError);
  }

  getCurrentProvider(): string {
    return this.currentProvider;
  }
}

export const router = new ProviderRouter();
export type { Message, ProviderResponse };
