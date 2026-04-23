export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ProviderResponse {
  content: string;
  provider: string;
  model: string;
}

export interface Provider {
  name: string;
  isAvailable(): boolean;
  chat(messages: Message[], systemPrompt: string): Promise<ProviderResponse>;
}
