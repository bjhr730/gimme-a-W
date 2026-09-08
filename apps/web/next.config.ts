import { fileURLToPath } from "node:url";
import { config } from "dotenv";
import type { NextConfig } from "next";

// Secrets live in the repo-root .env (two levels up). Vercel injects env vars directly.
config({ path: fileURLToPath(new URL("../../.env", import.meta.url)) });

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  transpilePackages: ["@gimme/db"],
  serverExternalPackages: ["postgres"],
  poweredByHeader: false,
  images: {
    remotePatterns: [{ protocol: "https", hostname: "a.espncdn.com" }],
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
