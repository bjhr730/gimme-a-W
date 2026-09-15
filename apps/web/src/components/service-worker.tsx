"use client";

import { useEffect } from "react";

/**
 * Registers /sw.js. The worker itself never serves a cached page -- see the
 * comment at the top of it -- so this costs nothing in freshness; what it buys
 * is an offline fallback and, more to the point, the "Install app" prompt, which
 * Chrome will not offer to a site without a service worker.
 *
 * Skipped in development, where an old worker outliving a rebuild is only ever a
 * source of confusion.
 */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // An install that fails leaves the app exactly as it was; nothing to do.
      });
    };
    if (document.readyState === "complete") register();
    else {
      window.addEventListener("load", register);
      return () => window.removeEventListener("load", register);
    }
  }, []);

  return null;
}
