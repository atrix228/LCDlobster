import Database from "better-sqlite3";
import * as fs from "fs";
import * as path from "path";
import { config } from "./config";

export interface HistoryMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface SessionData {
  channel: string;
  chat_id: string;
  metadata: Record<string, unknown>;
  updated_at: string;
}

let db: Database.Database;

export function initDb(): void {
  const dbPath = path.resolve(process.cwd(), config.db.path);
  const dbDir = path.dirname(dbPath);

  if (!fs.existsSync(dbDir)) {
    fs.mkdirSync(dbDir, { recursive: true });
  }

  db = new Database(dbPath);

  // Enable WAL mode for better concurrent read performance
  db.pragma("journal_mode = WAL");
  db.pragma("synchronous = NORMAL");
  db.pragma("foreign_keys = ON");

  db.exec(`
    CREATE TABLE IF NOT EXISTS conversations (
      id        INTEGER PRIMARY KEY AUTOINCREMENT,
      channel   TEXT    NOT NULL,
      chat_id   TEXT    NOT NULL,
      role      TEXT    NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
      content   TEXT    NOT NULL,
      timestamp INTEGER NOT NULL DEFAULT (unixepoch())
    );

    CREATE INDEX IF NOT EXISTS idx_conversations_chat
      ON conversations (channel, chat_id, timestamp);

    CREATE TABLE IF NOT EXISTS sessions (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      channel    TEXT    NOT NULL,
      chat_id    TEXT    NOT NULL,
      metadata   TEXT    NOT NULL DEFAULT '{}',
      updated_at TEXT    NOT NULL DEFAULT (datetime('now')),
      UNIQUE(channel, chat_id)
    );
  `);
}

export function addMessage(
  channel: string,
  chatId: string,
  role: "user" | "assistant" | "system",
  content: string
): void {
  const stmt = db.prepare(
    "INSERT INTO conversations (channel, chat_id, role, content) VALUES (?, ?, ?, ?)"
  );
  stmt.run(channel, chatId, role, content);
}

export function getHistory(
  channel: string,
  chatId: string,
  limit: number = config.db.max_history
): HistoryMessage[] {
  const stmt = db.prepare(`
    SELECT role, content
    FROM conversations
    WHERE channel = ? AND chat_id = ?
    ORDER BY timestamp DESC, id DESC
    LIMIT ?
  `);

  const rows = stmt.all(channel, chatId, limit) as HistoryMessage[];
  // Reverse to get chronological order (oldest first)
  return rows.reverse();
}

export function clearHistory(channel: string, chatId: string): void {
  const stmt = db.prepare(
    "DELETE FROM conversations WHERE channel = ? AND chat_id = ?"
  );
  stmt.run(channel, chatId);
}

export function upsertSession(
  channel: string,
  chatId: string,
  metadata: Record<string, unknown>
): void {
  const stmt = db.prepare(`
    INSERT INTO sessions (channel, chat_id, metadata, updated_at)
    VALUES (?, ?, ?, datetime('now'))
    ON CONFLICT(channel, chat_id) DO UPDATE SET
      metadata   = excluded.metadata,
      updated_at = excluded.updated_at
  `);
  stmt.run(channel, chatId, JSON.stringify(metadata));
}

export function getSession(
  channel: string,
  chatId: string
): SessionData | null {
  const stmt = db.prepare(
    "SELECT channel, chat_id, metadata, updated_at FROM sessions WHERE channel = ? AND chat_id = ?"
  );
  const row = stmt.get(channel, chatId) as
    | { channel: string; chat_id: string; metadata: string; updated_at: string }
    | undefined;

  if (!row) return null;

  return {
    channel: row.channel,
    chat_id: row.chat_id,
    metadata: JSON.parse(row.metadata) as Record<string, unknown>,
    updated_at: row.updated_at,
  };
}
