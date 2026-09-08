"use client";

import Link from "next/link";
import { useState } from "react";
import type { ParlayLeg } from "@/lib/queries";
import { LocalTime } from "./local-time";

function teamLabel(name: string, short: string | null): string {
  return short ?? name;
}

/** Turn a stored market row into the sentence a person would say out loud. */
export function describeLeg(leg: ParlayLeg): string {
  const home = teamLabel(leg.homeName, leg.homeShort);
  const away = teamLabel(leg.awayName, leg.awayShort);
  const subject = leg.subjectTeamName
    ? teamLabel(leg.subjectTeamName, leg.subjectTeamShort)
    : null;
  const player = leg.playerName ?? "Player";
  const overUnder = leg.selection.startsWith("under") ? "under" : "over";
  // stored as numeric(8,2), so 2.50 comes back where a person writes 2.5
  const raw = leg.line ?? leg.selection.split(" ").pop() ?? "";
  const parsed = Number(raw);
  const number = Number.isFinite(parsed) ? String(parsed) : String(raw);

  switch (leg.market) {
    case "match_result":
    case "win_probability":
      if (leg.selection === "home") return `${home} to win`;
      if (leg.selection === "away") return `${away} to win`;
      return "Draw";
    case "btts":
      return leg.selection === "yes" ? "Both teams to score" : "Both teams not to score";
    case "total_goals":
      return `${overUnder === "over" ? "Over" : "Under"} ${number} goals`;
    case "match_corners":
      return `${overUnder === "over" ? "Over" : "Under"} ${number} corners in the match`;
    case "corners":
      return `${subject ?? home} ${overUnder} ${number} corners`;
    case "shots_on_target":
      return `${subject ?? home} ${overUnder} ${number} shots on target`;
    case "anytime_scorer":
      return `${player} to score`;
    case "anytime_assist":
      return `${player} to assist`;
    case "anytime_td":
      return `${player} to score a touchdown`;
    case "player_shots_on_target":
      return `${player} ${leg.selection === "over 1.5" ? "2+" : "1+"} shots on target`;
    default:
      return `${leg.market.replace(/_/g, " ")} ${leg.selection}`.trim();
  }
}

function pct(p: number): string {
  if (p >= 0.1) return `${(p * 100).toFixed(1)}%`;
  if (p >= 0.001) return `${(p * 100).toFixed(2)}%`;
  return `${(p * 100).toExponential(1)}%`;
}

/** Fair price for a probability, with no bookmaker margin applied. */
function americanFromProbability(p: number): string {
  if (p <= 0 || p >= 1) return "–";
  const decimal = 1 / p;
  const american = decimal >= 2 ? (decimal - 1) * 100 : -100 / (decimal - 1);
  return `${american > 0 ? "+" : ""}${Math.round(american)}`;
}

export function ParlayBuilder({ legs, day }: { legs: ParlayLeg[]; day: string }) {
  const max = Math.min(20, legs.length);
  const [count, setCount] = useState(Math.min(4, max));
  const chosen = legs.slice(0, count);
  const combined = chosen.reduce((acc, l) => acc * l.probability, 1);
  const decimal = combined > 0 ? 1 / combined : 0;
  const dayLabel = new Date(`${day}T12:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });

  return (
    <>
      <section className="rounded-md border-2 border-pitch/60 bg-surface">
        <div className="grid gap-3 border-b border-line p-4 sm:grid-cols-[1fr_auto] sm:items-end">
          <div>
            <p className="label text-[11px] text-muted">{dayLabel}</p>
            <p className="display text-3xl font-extrabold leading-none">
              {count} legs
            </p>
            <label className="mt-3 block">
              <span className="label text-[11px] text-muted">Legs: 2 to {max}</span>
              <input
                type="range"
                min={2}
                max={Math.max(max, 2)}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                className="mt-1 w-full accent-[var(--color-pitch,#1f7a4d)]"
                aria-label={`Number of legs, ${count}`}
              />
            </label>
            <div className="mt-2 flex flex-wrap gap-1">
              {[2, 3, 4, 6, 8, 10, 15, 20]
                .filter((n) => n <= max)
                .map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setCount(n)}
                    className={`label rounded border px-2 py-1 text-[11px] ${
                      n === count
                        ? "border-pitch bg-pitch-soft text-pitch"
                        : "border-line-strong text-ink-2 hover:border-pitch hover:text-pitch"
                    }`}
                  >
                    {n}
                  </button>
                ))}
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-2 sm:w-64">
            <div className="rounded-md bg-surface-2/60 px-3 py-2">
              <dt className="label text-[11px] text-muted">All land</dt>
              <dd className="display tnum text-2xl font-extrabold leading-tight">
                {pct(combined)}
              </dd>
            </div>
            <div className="rounded-md bg-surface-2/60 px-3 py-2">
              <dt className="label text-[11px] text-muted">Fair price</dt>
              <dd className="display tnum text-2xl font-extrabold leading-tight">
                {americanFromProbability(combined)}
              </dd>
              <dd className="tnum text-xs text-ink-2">{decimal.toFixed(2)} decimal</dd>
            </div>
          </dl>
        </div>

        <ol className="divide-y divide-line">
          {chosen.map((leg, i) => (
            <li key={`${leg.gameId}-${leg.market}-${leg.selection}`} className="px-3 py-2">
              <div className="flex items-baseline gap-2">
                <span className="display tnum w-6 shrink-0 text-lg font-extrabold text-muted">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <Link href={`/games/${leg.gameId}`} className="block hover:text-pitch">
                    <span className="block text-[15px] font-semibold">{describeLeg(leg)}</span>
                  </Link>
                  <span className="label block text-[11px] text-muted">
                    {teamLabel(leg.awayName, leg.awayShort)} at {teamLabel(leg.homeName, leg.homeShort)}
                    {" · "}
                    {leg.competitionName}
                    {" · "}
                    <LocalTime iso={leg.kickoff.toISOString()} mode="time" />
                  </span>
                </div>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-surface-2 sm:block">
                    <span
                      className="block h-full bg-pitch"
                      style={{ width: `${Math.round(leg.probability * 100)}%` }}
                    />
                  </span>
                  <span className="tnum w-11 text-right font-semibold">
                    {Math.round(leg.probability * 100)}%
                  </span>
                </span>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <p className="mt-3 max-w-[70ch] text-xs text-muted">
        One leg per game, because two calls on the same match rise and fall together and
        multiplying them would flatter the parlay. Legs above 95% are left out: they add
        nothing and no book prices them. Legs drawn from the same market share one model,
        so if that model runs hot they miss together and the real chance is lower than the
        product suggests. The fair price carries no bookmaker margin, so a real ticket will
        pay less. These are model probabilities, not betting advice.
      </p>
    </>
  );
}
