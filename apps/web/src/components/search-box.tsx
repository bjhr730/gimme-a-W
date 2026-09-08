"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { SearchGame, SearchResult } from "@/lib/search";
import { LocalTime } from "./local-time";

const EXAMPLES = ["arsenal chelsea", "seahawks", "premier league table", "nfl sunday", "tomorrow", "mahomes"];

type Item = { href: string; key: string };

function GameRow({ g }: { g: SearchGame }) {
  const played = g.status === "final" || g.status === "in_progress";
  return (
    <span className="grid grid-cols-[1fr_auto] items-center gap-2">
      <span className="min-w-0">
        <span className="label block text-[10px] text-muted">{g.competitionName}</span>
        <span className="block truncate text-[15px]">
          {g.away.shortName ?? g.away.name}
          {played ? <span className="tnum font-semibold"> {g.awayScore}</span> : null}
          <span className="text-muted"> at </span>
          {g.home.shortName ?? g.home.name}
          {played ? <span className="tnum font-semibold"> {g.homeScore}</span> : null}
        </span>
      </span>
      <span className="label text-right text-[11px] text-ink-2">
        {g.status === "final" ? "FT" : g.status === "in_progress" ? <span className="text-live">Live</span> : null}{" "}
        <LocalTime iso={g.kickoff} mode="datetime" />
      </span>
    </span>
  );
}

export function SearchBox({ variant }: { variant: "header" | "page" }) {
  const router = useRouter();
  const [open, setOpen] = useState(variant === "page");
  const [q, setQ] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const search = useCallback(async (text: string) => {
    abortRef.current?.abort();
    if (text.trim().length < 2) {
      setResult(null);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(text)}`, { signal: controller.signal });
      if (res.ok) setResult((await res.json()) as SearchResult);
    } catch {
      // aborted or offline: keep the previous result
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void search(q), 160);
    return () => clearTimeout(id);
  }, [q, search]);

  useEffect(() => {
    if (variant !== "header") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes((e.target as HTMLElement).tagName)) {
        e.preventDefault();
        setOpen(true);
        setTimeout(() => inputRef.current?.focus(), 0);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [variant]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const items: Item[] = [];
  if (result) {
    for (const p of result.pages) items.push({ href: p.href, key: `p-${p.href}` });
    for (const g of result.games) items.push({ href: `/games/${g.id}`, key: `g-${g.id}` });
    for (const t of result.teams) items.push({ href: `/teams/${t.id}`, key: `t-${t.id}` });
    for (const p of result.players) items.push({ href: `/players/${p.id}`, key: `pl-${p.id}` });
    for (const l of result.leagues) items.push({ href: `/standings/${l.slug}`, key: `l-${l.slug}` });
  }
  useEffect(() => setActive(0), [result]);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, Math.max(items.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      const target = items[active] ?? items[0];
      if (target) {
        setOpen(variant === "page");
        router.push(target.href);
      }
    }
  }

  const list = (
    <div className="max-h-[70vh] overflow-y-auto">
      {!result || (q.trim().length < 2) ? (
        <div className="px-4 py-3 text-sm text-ink-2">
          <p className="mb-2">Try a team, two teams, a player, a league, or a day.</p>
          <ul className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((ex) => (
              <li key={ex}>
                <button
                  type="button"
                  onClick={() => setQ(ex)}
                  className="label rounded border border-line-strong px-2 py-1 text-[11px] text-ink-2 hover:border-pitch hover:text-pitch"
                >
                  {ex}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          {result.interpretation ? (
            <p className="label border-b border-line px-4 py-2 text-[11px] text-muted">
              {result.interpretation}
              {loading ? " …" : ""}
            </p>
          ) : null}
          {items.length === 0 && !loading ? (
            <p className="px-4 py-4 text-sm text-ink-2">Nothing matches “{q}”.</p>
          ) : null}
          <ul>
            {items.map((item, i) => {
              const cls = `block border-b border-line px-4 py-2 last:border-b-0 ${i === active ? "bg-pitch-soft" : "hover:bg-surface-2/60"}`;
              const onClick = () => setOpen(variant === "page");
              if (item.key.startsWith("p-")) {
                const p = result.pages.find((x) => `p-${x.href}` === item.key)!;
                return (
                  <li key={item.key}>
                    <Link href={item.href} className={cls} onClick={onClick} onMouseEnter={() => setActive(i)}>
                      <span className="label block text-[10px] text-muted">{p.hint}</span>
                      <span className="text-[15px] text-pitch">{p.label} →</span>
                    </Link>
                  </li>
                );
              }
              if (item.key.startsWith("g-")) {
                const g = result.games.find((x) => `g-${x.id}` === item.key)!;
                return (
                  <li key={item.key}>
                    <Link href={item.href} className={cls} onClick={onClick} onMouseEnter={() => setActive(i)}>
                      <GameRow g={g} />
                    </Link>
                  </li>
                );
              }
              if (item.key.startsWith("t-")) {
                const t = result.teams.find((x) => `t-${x.id}` === item.key)!;
                return (
                  <li key={item.key}>
                    <Link href={item.href} className={`${cls} flex items-center gap-2`} onClick={onClick} onMouseEnter={() => setActive(i)}>
                      {t.logoUrl ? <img src={t.logoUrl} alt="" className="h-6 w-6 object-contain" /> : <span className="h-6 w-6 rounded-full bg-surface-2" />}
                      <span className="text-[15px]">{t.name}</span>
                      <span className="label ml-auto text-[10px] text-muted">{t.sportId === "soccer" ? "Club" : "Team"}{t.abbreviation ? ` · ${t.abbreviation}` : ""}</span>
                    </Link>
                  </li>
                );
              }
              if (item.key.startsWith("pl-")) {
                const p = result.players.find((x) => `pl-${x.id}` === item.key)!;
                return (
                  <li key={item.key}>
                    <Link href={item.href} className={`${cls} flex items-center gap-2`} onClick={onClick} onMouseEnter={() => setActive(i)}>
                      {p.headshotUrl ? <img src={p.headshotUrl} alt="" className="h-6 w-6 rounded-full bg-surface-2 object-cover object-top" /> : <span className="h-6 w-6 rounded-full bg-surface-2" />}
                      <span className="text-[15px]">{p.fullName}</span>
                      <span className="label ml-auto text-[10px] text-muted">Player{p.position ? ` · ${p.position}` : ""}</span>
                    </Link>
                  </li>
                );
              }
              const l = result.leagues.find((x) => `l-${x.slug}` === item.key)!;
              return (
                <li key={item.key}>
                  <Link href={item.href} className={cls} onClick={onClick} onMouseEnter={() => setActive(i)}>
                    <span className="text-[15px]">{l.name}</span>
                    <span className="label ml-2 text-[10px] text-muted">League · table</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );

  const input = (
    <input
      ref={inputRef}
      type="search"
      value={q}
      onChange={(e) => setQ(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder="Team, matchup, player, league or day…"
      aria-label="Search games, teams, players and leagues"
      autoComplete="off"
      className="w-full bg-transparent px-3 py-2 text-base text-ink placeholder:text-muted focus:outline-none"
    />
  );

  if (variant === "page") {
    return (
      <div className="rounded-md border border-line-strong bg-surface">
        <div className="border-b border-line">{input}</div>
        {list}
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="label inline-flex h-8 items-center gap-2 rounded border border-line-strong px-2 text-xs text-ink-2 hover:border-pitch hover:text-pitch"
        aria-label="Open search"
      >
        <span aria-hidden="true">⌕</span>
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden rounded border border-line px-1 text-[10px] text-muted md:inline">/</kbd>
      </button>
      {open ? (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Search">
          <button
            type="button"
            aria-label="Close search"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-ink/40"
          />
          <div className="absolute inset-x-0 top-0 mx-auto max-w-2xl p-2 sm:top-10 sm:p-4">
            <div className="overflow-hidden rounded-md border border-line-strong bg-surface shadow-2xl">
              <div className="flex items-center border-b border-line">
                {input}
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="label px-3 text-xs text-muted hover:text-ink"
                >
                  Esc
                </button>
              </div>
              {list}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
