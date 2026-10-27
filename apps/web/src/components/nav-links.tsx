"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Today", glyph: "◉" },
  { href: "/soccer", label: "Soccer", glyph: "⚽" },
  { href: "/nfl", label: "NFL", glyph: "🏈" },
  { href: "/parlay", label: "Parlay", glyph: "🎟" },
  { href: "/models", label: "Models", glyph: "◔" },
];

export function NavLinks({ variant }: { variant: "top" | "bottom" }) {
  const pathname = usePathname();
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  if (variant === "top") {
    return (
      <ul className="flex items-center gap-1">
        {LINKS.map((l) => (
          <li key={l.href}>
            <Link
              href={l.href}
              className={`label rounded px-3 py-1.5 text-sm ${
                active(l.href) ? "bg-pitch-soft text-pitch" : "text-ink-2 hover:text-ink"
              }`}
            >
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    );
  }

  // Flex rather than a fixed column count: this was `grid-cols-6` and went
  // lopsided the moment a tab was removed, leaving an empty sixth column and
  // every tab shoved left. Equal flex children divide the bar by however many
  // links there are, so adding or dropping one stays centred.
  return (
    <ul className="flex">
      {LINKS.map((l) => (
        <li key={l.href} className="flex-1">
          <Link
            href={l.href}
            aria-current={active(l.href) ? "page" : undefined}
            className={`flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${
              active(l.href) ? "text-pitch" : "text-muted"
            }`}
          >
            <span aria-hidden="true" className="text-lg leading-none">
              {l.glyph}
            </span>
            <span className="label">{l.label}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
