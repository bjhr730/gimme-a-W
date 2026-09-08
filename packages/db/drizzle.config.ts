import { config } from "dotenv";
import { fileURLToPath } from "node:url";
import { defineConfig } from "drizzle-kit";

// Secrets live in the repo-root .env, two levels up from this package.
config({ path: fileURLToPath(new URL("../../.env", import.meta.url)) });

// Migrations run against the direct (non-pooled) Neon URL. Generation works offline.
export default defineConfig({
  dialect: "postgresql",
  schema: "./src/schema.ts",
  out: "./drizzle",
  dbCredentials: {
    url: process.env.DIRECT_URL ?? process.env.DATABASE_URL ?? "postgresql://localhost/gimme",
  },
  strict: true,
  verbose: true,
});
