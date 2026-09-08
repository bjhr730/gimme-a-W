"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

/** The theme in effect right now: the pinned one, else what the OS asks for. */
function effectiveTheme(): Theme {
  const pinned = document.documentElement.dataset.theme;
  if (pinned === "light" || pinned === "dark") return pinned;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Light / dark switch. The choice is stored in localStorage and re-applied before
 * first paint by the inline script in the root layout, so there is no flash.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    setTheme(effectiveTheme());
    // Follow the OS again if the user never pinned a theme and flips their system setting.
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (!document.documentElement.dataset.theme) setTheme(media.matches ? "dark" : "light");
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  function toggle() {
    const next: Theme = (theme ?? effectiveTheme()) === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      // private mode or blocked storage: the choice still applies for this page view
    }
    setTheme(next);
  }

  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
      className="inline-flex h-8 w-8 items-center justify-center rounded border border-line-strong text-base leading-none text-ink-2 hover:border-pitch hover:text-pitch focus-visible:outline focus-visible:outline-2 focus-visible:outline-pitch"
    >
      <span aria-hidden="true" suppressHydrationWarning>
        {theme === null ? "◐" : dark ? "☀" : "☾"}
      </span>
    </button>
  );
}
