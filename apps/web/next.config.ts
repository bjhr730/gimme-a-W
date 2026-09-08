import { fileURLToPath } from "node:url";
import { config } from "dotenv";
import type { NextConfig } from "next";

// Secrets live in the repo-root .env (two levels up). Vercel injects env vars directly.
config({ path: fileURLToPath(new URL("../../.env", import.meta.url)) });

const nextConfig: NextConfig = {
  transpilePackages: ["@gimme/db"],
  serverExternalPackages: ["postgres"],
  images: {
    remotePatterns: [{ protocol: "https", hostname: "a.espncdn.com" }],
  },
};

export default nextConfig;
