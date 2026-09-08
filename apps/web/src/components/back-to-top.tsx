"use client";

import { useEffect, useState } from "react";

const SHOW_AFTER_PX = 600;

/** Floating button that appears once the page is scrolled a screen or more. */
export function BackToTop() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        setVisible(window.scrollY > SHOW_AFTER_PX);
        ticking = false;
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function scrollToTop() {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    // hand focus to the page top so keyboard users continue from there
    document.querySelector<HTMLElement>("main")?.focus({ preventScroll: true });
  }

  return (
    <button
      type="button"
      onClick={scrollToTop}
      aria-label="Back to top"
      aria-hidden={!visible}
      tabIndex={visible ? 0 : -1}
      className={`fixed right-3 z-30 flex h-11 w-11 items-center justify-center rounded-full border border-line-strong bg-surface text-ink shadow-lg transition-opacity duration-200 hover:border-pitch hover:text-pitch focus-visible:outline focus-visible:outline-2 focus-visible:outline-pitch motion-reduce:transition-none ${
        visible ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
      style={{ bottom: "calc(64px + env(safe-area-inset-bottom) + 12px)" }}
      data-desktop-bottom
    >
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 19V5" />
        <path d="M5 12l7-7 7 7" />
      </svg>
    </button>
  );
}
