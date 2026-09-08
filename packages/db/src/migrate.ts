import "dotenv/config";
import { fileURLToPath } from "node:url";
import { drizzle } from "drizzle-orm/postgres-js";
import { migrate } from "drizzle-orm/postgres-js/migrator";
import postgres from "postgres";

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) {
  console.error("Set DIRECT_URL (preferred) or DATABASE_URL before running migrations.");
  process.exit(1);
}

const sql = postgres(url, { max: 1 });
const db = drizzle(sql);
const migrationsFolder = fileURLToPath(new URL("../drizzle", import.meta.url));

try {
  await migrate(db, { migrationsFolder });
  console.log("Migrations applied.");
} finally {
  await sql.end();
}
