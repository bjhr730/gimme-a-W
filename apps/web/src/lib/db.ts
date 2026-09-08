import { createDb, type Database } from "@gimme/db";

// One client per server process. Next.js reloads modules in dev, so park it on globalThis.
const globalForDb = globalThis as unknown as { __gimmeDb?: Database };

export function db(): Database {
  if (!globalForDb.__gimmeDb) {
    globalForDb.__gimmeDb = createDb();
  }
  return globalForDb.__gimmeDb;
}
