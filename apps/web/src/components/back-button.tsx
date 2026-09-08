"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/** The tabs are their own destinations, so there is nothing to go back from. */
const ROOTS = new Set([
  "/",
  "/soccer",
  "/nfl",
  "/cfb",
  "/parlay",
  "/models",
  "/status",
  "/search",
]);

/**
 * Where to land when this page was opened directly (a shared link, a bookmark)
 * and the browser has no history of its own to step back through.
 */
function fallbackFor(pathname: string): string {
  if (pathname.startsWith("/standings")) return "/soccer";
  if (pathname.startsWith("/players") || pathname.startsWith("/teams")) return "/search";
  return "/";
}

export function BackButton() {
  const router = useRouter();
  const pathname = usePathname();
  // Rendered only after mount: whether history exists is a browser fact, and
  // guessing it on the server would flash the wrong control.
  const [canGoBack, setCanGoBack] = useState(false);

  useEffect(() => {
    setCanGoBack(window.history.length > 1);
  }, [pathname]);

  if (ROOTS.has(pathname)) return null;

  function goBack() {
    if (canGoBack) router.back();
    else router.push(fallbackFor(pathname));
  }

  return (
    <button
      type="button"
      onClick={goBack}
      aria-label="Go back"
      className="label -ml-1 flex h-8 shrink-0 items-center gap-1 rounded border border-line-strong px-2 text-xs text-ink-2 hover:border-pitch hover:text-pitch focus-visible:outline focus-visible:outline-2 focus-visible:outline-pitch"
    >
      <svg
        aria-hidden="true"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M15 18l-6-6 6-6" />
      </svg>
      <span className="hidden sm:inline">Back</span>
    </button>
  );
}
