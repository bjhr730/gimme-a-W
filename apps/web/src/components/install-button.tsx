"use client";

import { useEffect, useState } from "react";

/**
 * The event Chrome fires when it decides the app is installable. It is not in
 * lib.dom, because it is not in any spec -- Chromium only.
 */
interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
  readonly userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/**
 * Offers to install the app, and only when the browser says it can be installed.
 *
 * Chrome fires `beforeinstallprompt` once it is satisfied with the manifest, the
 * icons and the service worker, then waits for its own engagement heuristic
 * before volunteering anything in the menu. Catching the event and keeping it
 * means the offer is there the moment it is possible rather than whenever Chrome
 * gets round to it -- and it disappears again on browsers that never fire it, or
 * once the app is already installed.
 */
export function InstallButton() {
  const [prompt, setPrompt] = useState<InstallPromptEvent | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Already running from the home screen: there is nothing left to install.
    if (window.matchMedia("(display-mode: standalone)").matches) return;

    const onAvailable = (event: Event) => {
      // Keep the event: it can only be prompted with later, and only once.
      event.preventDefault();
      setPrompt(event as InstallPromptEvent);
    };
    const onInstalled = () => setPrompt(null);

    window.addEventListener("beforeinstallprompt", onAvailable);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onAvailable);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (!prompt) return null;

  async function install() {
    if (!prompt || busy) return;
    setBusy(true);
    try {
      await prompt.prompt();
      const { outcome } = await prompt.userChoice;
      // Spent either way: Chrome will fire a fresh event if it is still installable.
      if (outcome === "accepted") setPrompt(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={install}
      disabled={busy}
      aria-label="Install Gimme a W"
      title="Install this app"
      className="inline-flex h-8 items-center gap-1.5 rounded border border-line-strong px-2 text-xs font-semibold uppercase tracking-wide text-ink-2 hover:border-pitch hover:text-pitch focus-visible:outline focus-visible:outline-2 focus-visible:outline-pitch disabled:opacity-60"
    >
      <span aria-hidden="true" className="text-base leading-none">
        ⤓
      </span>
      <span className="hidden sm:inline">Install</span>
    </button>
  );
}
