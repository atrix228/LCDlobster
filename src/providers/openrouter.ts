import OpenAI from "openai";
import { config } from "../config";
import { Message, Provider, ProviderResponse } from "./types";

export class OpenRouterProvider implements Provider {
  readonly name = "openrouter";

  private get cfg() {
    return config.providers.openrouter;
  }

  private buildClient(): OpenAI {
    return new OpenAI({
      apiKey: this.cfg.api_key,
      baseURL: "https://openrouter.ai/api/v1",
      defaultHeaders: {
        "HTTP-Referer": "https://github.com/lcdlobster",
        "X-Title": "LCDLobster",
      },
    });
  }

  isAvailable(): boolean {
    return typeof this.cfg.api_key === "string" && this.cfg.api_key.trim().length > 0;
  }

  async chat(messages: Message[], systemPrompt: string): Promise<ProviderResponse> {
    const { model } = this.cfg;
    const client = this.buildClient();

    // Prepend the system message; filter out any existing system messages from history
    const composed: OpenAI.Chat.ChatCompletionMessageParam[] = [
      { role: "system", content: systemPrompt },
      ...messages
        .filter((m) => m.role !== "system")
        .map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        })),
    ];

    let completion;
    try {
      completion = await client.chat.completions.create({
        model,
        messages: composed,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      throw new Error(`[openrouter] Request failed: ${message}`);
    }

    const content = completion.choices[0]?.message?.content;
    if (typeof content !== "string" || content.trim().length === 0) {
      throw new Error("[openrouter] No content in response");
    }

    return {
      content: content.trim(),
      provider: this.name,
      model,
    };
  }
}
