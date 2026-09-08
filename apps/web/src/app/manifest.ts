import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Gimme a W",
    short_name: "Gimme a W",
    description: "Scores, standings, stats and predictions for soccer, the NFL and college football.",
    start_url: "/",
    display: "standalone",
    background_color: "#f2f4f0",
    theme_color: "#1d7a46",
    orientation: "portrait",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
