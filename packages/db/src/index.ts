import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema.js";

export * from "./schema.js";
export { schema };

export type Database = ReturnType<typeof createDb>;

/**
 * Create a Drizzle client. The web app calls this once per server process
 * with the pooled DATABASE_URL. Neon's pooler does not support prepared
 * statements, hence `prepare: false`.
 */
export function createDb(url = process.env.DATABASE_URL) {
  if (!url) throw new Error("DATABASE_URL is not set");
  const client = postgres(url, { prepare: false, max: 10 });
  return drizzle(client, { schema });
}
