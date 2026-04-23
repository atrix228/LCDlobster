import Anthropic from "@anthropic-ai/sdk";
import { config } from "../config";
import { Message, Provider, ProviderResponse } from "./types";

export class AnthropicProvider implements Provider {
  readonly name = "anthropic";

  private get cfg() {
    return config.providers.anthropic;
  }

  isAvailable(): boolean {
    return typeof this.cfg.api_key === "string" && this.cfg.api_key.trim().length > 0;
  }

  async chat(messages: Message[], systemPrompt: string): Promise<ProviderResponse> {
    const { api_key, model } = this.cfg;

    const client = new Anthropic({ apiKey: api_key });

    // Filter out system messages from history; they are passed via the system param
    const composed: Anthropic.MessageParam[] = messages
      .filter((m) => m.role !== "system")
      .map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
      }));

    // Anthropic requires at least one user message and the last message must be from user
    if (composed.length === 0 || composed[composed.length - 1]?.role !== "user") {
      throw new Error("[anthropic] Message list must end with a user message");
    }

    let response;
    try {
      response = await client.messages.create({
        model,
        max_tokens: 1024,
        system: systemPrompt,
        messages: composed,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      throw new Error(`[anthropic] Request failed: ${message}`);
    }

    // Extract text from content blocks
    const textContent = response.content
      .filter((block): block is Anthropic.TextBlock => block.type === "text")
      .map((block) => block.text)
      .join("");

    if (!textContent.trim()) {
      throw new Error("[anthropic] No text content in response");
    }

    return {
      content: textContent.trim(),
      provider: this.name,
      model,
    };
  }
}
