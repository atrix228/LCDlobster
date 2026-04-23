import axios from "axios";
import { config } from "../config";
import { Message, Provider, ProviderResponse } from "./types";

interface MiniMaxMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

interface MiniMaxChoice {
  message: {
    role: string;
    content: string;
  };
  finish_reason: string;
}

interface MiniMaxResponse {
  choices: MiniMaxChoice[];
  model: string;
  id: string;
}

export class MiniMaxProvider implements Provider {
  readonly name = "minimax";

  private get cfg() {
    return config.providers.minimax;
  }

  isAvailable(): boolean {
    return typeof this.cfg.api_key === "string" && this.cfg.api_key.trim().length > 0;
  }

  async chat(messages: Message[], systemPrompt: string): Promise<ProviderResponse> {
    const { api_key, model, base_url } = this.cfg;

    const payload: MiniMaxMessage[] = [
      { role: "system", content: systemPrompt },
      ...messages.filter((m) => m.role !== "system").map((m) => ({
        role: m.role,
        content: m.content,
      })),
    ];

    let response;
    try {
      response = await axios.post<MiniMaxResponse>(
        `${base_url}/text/chatcompletion_v2`,
        {
          model,
          messages: payload,
          stream: false,
        },
        {
          headers: {
            Authorization: `Bearer ${api_key}`,
            "Content-Type": "application/json",
          },
          timeout: 60000,
        }
      );
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      throw new Error(`[minimax] Request failed: ${message}`);
    }

    const choices = response.data?.choices;
    if (!Array.isArray(choices) || choices.length === 0) {
      throw new Error("[minimax] Empty choices in response");
    }

    const content = choices[0]?.message?.content;
    if (typeof content !== "string" || content.trim().length === 0) {
      throw new Error("[minimax] No content in response");
    }

    return {
      content: content.trim(),
      provider: this.name,
      model,
    };
  }
}
