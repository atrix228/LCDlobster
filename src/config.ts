import * as fs from "fs";
import * as path from "path";
import * as TOML from "toml";

export interface BotConfig {
  name: string;
  system_prompt: string;
}

export interface MiniMaxProviderConfig {
  api_key: string;
  model: string;
  base_url: string;
}

export interface OpenRouterProviderConfig {
  api_key: string;
  model: string;
  base_url: string;
}

export interface AnthropicProviderConfig {
  api_key: string;
  model: string;
}

export interface ProvidersConfig {
  priority: string[];
  minimax: MiniMaxProviderConfig;
  openrouter: OpenRouterProviderConfig;
  anthropic: AnthropicProviderConfig;
}

export interface WhatsAppChannelConfig {
  enabled: boolean;
  session_path: string;
}

export interface HttpChannelConfig {
  enabled: boolean;
  port: number;
  host: string;
}

export interface ChannelsConfig {
  whatsapp: WhatsAppChannelConfig;
  http: HttpChannelConfig;
}

export interface DisplayConfig {
  socket_path: string;
  enabled: boolean;
}

export interface DbConfig {
  path: string;
  max_history: number;
}

export interface Config {
  bot: BotConfig;
  providers: ProvidersConfig;
  channels: ChannelsConfig;
  display: DisplayConfig;
  db: DbConfig;
}

function loadConfig(): Config {
  const configPath = path.join(process.cwd(), "config.toml");

  if (!fs.existsSync(configPath)) {
    throw new Error(`Config file not found at ${configPath}`);
  }

  const raw = fs.readFileSync(configPath, "utf-8");
  const parsed = TOML.parse(raw) as Config;

  // Validate required structure
  if (!parsed.bot) throw new Error("Config missing [bot] section");
  if (!parsed.providers) throw new Error("Config missing [providers] section");
  if (!parsed.channels) throw new Error("Config missing [channels] section");
  if (!parsed.display) throw new Error("Config missing [display] section");
  if (!parsed.db) throw new Error("Config missing [db] section");

  if (!Array.isArray(parsed.providers.priority) || parsed.providers.priority.length === 0) {
    throw new Error("Config providers.priority must be a non-empty array");
  }

  // Validate that at least one provider has an api_key set
  const providerMap: Record<string, { api_key?: string }> = {
    minimax: parsed.providers.minimax,
    openrouter: parsed.providers.openrouter,
    anthropic: parsed.providers.anthropic,
  };

  const hasAtLeastOneKey = parsed.providers.priority.some(
    (name) => providerMap[name]?.api_key && providerMap[name].api_key!.trim().length > 0
  );

  if (!hasAtLeastOneKey) {
    throw new Error(
      "No provider API keys configured. Set at least one api_key in config.toml under [providers.minimax], [providers.openrouter], or [providers.anthropic]."
    );
  }

  return parsed;
}

export const config: Config = loadConfig();
