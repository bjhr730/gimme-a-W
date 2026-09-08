import "dotenv/config";
import { defineConfig } from "drizzle-kit";

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
