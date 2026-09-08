import type { PredictionRow } from "@/lib/queries";
import { signed } from "@/lib/format";

type Team = { id: number; name: string; shortName: string | null; abbreviation: string | null };

function pct(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return `${Math.round(Number(v) * 100)}%`;
}

function Bar({ home, away, labelHome, labelAway }: { home: number; away: number; labelHome: string; labelAway: string }) {
  const draw = Math.max(0, 1 - home - away);
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-2">
        <div className="bg-leather" style={{ width: `${away * 100}%` }} />
        {draw > 0.005 ? <div className="bg-line-strong" style={{ width: `${draw * 100}%` }} /> : null}
        <div className="bg-pitch" style={{ width: `${home * 100}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-xs">
        <span className="tnum">
          <span className="label text-leather">{labelAway}</span> {pct(away)}
        </span>
        {draw > 0.005 ? <span className="tnum text-muted">Draw {pct(draw)}</span> : null}
        <span className="tnum">
          {pct(home)} <span className="label text-pitch">{labelHome}</span>
        </span>
      </div>
    </div>
  );
}

function explain(e: Record<string, unknown>, home: Team, away: Team, soccer: boolean): string[] {
  const out: string[] = [];
  const h = home.shortName ?? home.name;
  const a = away.shortName ?? away.name;
  if (!soccer) {
    const eh = Number(e.elo_home);
    const ea = Number(e.elo_away);
    if (Number.isFinite(eh) && Number.isFinite(ea)) {
      const diff = Math.round(eh - ea);
      out.push(diff === 0 ? `Even on Elo (${eh} each)` : `${diff > 0 ? h : a} ${Math.abs(diff)} Elo points stronger (${eh} vs ${ea})`);
    }
    const edge = Number(e.home_edge);
    if (edge > 0) out.push(`Home edge worth ${edge} Elo points`);
    const rh = Number(e.rest_home);
    const ra = Number(e.rest_away);
    if (Number.isFinite(rh) && Number.isFinite(ra) && rh !== ra) {
      out.push(`${rh > ra ? h : a} better rested (${Math.max(rh, ra)} vs ${Math.min(rh, ra)} days)`);
    }
    const fh = Number(e.form_home);
    const fa = Number(e.form_away);
    if (Number.isFinite(fh) && Number.isFinite(fa)) {
      out.push(`Last 5 average margin: ${h} ${signed(Math.round(fh))}, ${a} ${signed(Math.round(fa))}`);
    }
  } else {
    const ah = Number(e.attack_home);
    const aa = Number(e.attack_away);
    const dh = Number(e.defence_home);
    const da = Number(e.defence_away);
    if ([ah, aa, dh, da].every(Number.isFinite)) {
      out.push(`Attack: ${h} ${signed(Number(ah.toFixed(2)))}, ${a} ${signed(Number(aa.toFixed(2)))} (league average 0)`);
      out.push(`Defence: ${h} ${signed(Number(dh.toFixed(2)))}, ${a} ${signed(Number(da.toFixed(2)))}`);
    }
    const edge = Number(e.home_edge);
    if (edge > 0) out.push(`Home edge ${Math.round(edge * 100)}% more goals`);
  }
  if (typeof e.blend === "string") out.push(e.blend === "model only" ? "No market line, model only" : `Blend: ${e.blend}`);
  return out;
}

export function PredictionPanel({
  rows,
  home,
  away,
  soccer,
}: {
  rows: PredictionRow[];
  home: Team;
  away: Team;
  soccer: boolean;
}) {
  if (rows.length === 0) return null;
  const find = (market: string, selection: string) => rows.find((r) => r.market === market && r.selection === selection);
  const explanationRow = rows.find((r) => r.explanation);
  const e = (explanationRow?.explanation ?? {}) as Record<string, unknown>;
  const hLabel = home.abbreviation ?? home.shortName ?? home.name;
  const aLabel = away.abbreviation ?? away.shortName ?? away.name;

  // true once we know a closing total exists to compare the model against
  let showTotalsCaveat = false;
  let bar: React.ReactNode = null;
  const details: { label: string; value: string; sub?: string }[] = [];
  if (soccer) {
    const ph = Number(find("match_result", "home")?.probability ?? 0);
    const pa = Number(find("match_result", "away")?.probability ?? 0);
    bar = <Bar home={ph} away={pa} labelHome={hLabel} labelAway={aLabel} />;
    const tg = find("team_goals", "home");
    const ta = find("team_goals", "away");
    const over = find("total_goals", "over 2.5");
    const btts = find("btts", "yes");
    if (tg && ta) details.push({ label: "Expected goals", value: `${Number(tg.mean).toFixed(1)} – ${Number(ta.mean).toFixed(1)}` });
    if (over) details.push({ label: "Over 2.5 goals", value: pct(over.probability), sub: `expected total ${Number(over.mean).toFixed(1)}` });
    if (btts) details.push({ label: "Both teams score", value: pct(btts.probability) });
  } else {
    const ph = Number(find("win_probability", "home")?.probability ?? 0);
    // set below when a closing total exists to compare against
    bar = <Bar home={ph} away={1 - ph} labelHome={hLabel} labelAway={aLabel} />;
    const spread = find("spread", "home");
    const total = find("total_points", "");
    if (spread) {
      const m = Number(spread.mean);
      const q = (spread.quantiles ?? {}) as { p25?: number; p75?: number };
      const fav = m >= 0 ? hLabel : aLabel;
      details.push({
        label: "Expected margin",
        value: `${fav} by ${Math.abs(m).toFixed(1)}`,
        sub: spread.line !== null ? `market ${hLabel} ${signed(Number(spread.line))}` : q.p25 !== undefined ? `middle half ${signed(Number(q.p25))} to ${signed(Number(q.p75))}` : undefined,
      });
    }
    if (total) {
      // The spread between this and the line reads as a disagreement until you
      // see the range, which is wide enough to swallow most of it.
      const q = (total.quantiles ?? {}) as { p25?: number; p75?: number };
      const parts = [
        total.line !== null ? `market ${Number(total.line).toFixed(1)}` : null,
        q.p25 !== undefined && q.p75 !== undefined
          ? `middle half ${Math.round(Number(q.p25))}–${Math.round(Number(q.p75))}`
          : null,
      ].filter(Boolean);
      details.push({
        label: "Expected total",
        value: Number(total.mean).toFixed(1),
        sub: parts.length ? parts.join(" · ") : undefined,
      });
      showTotalsCaveat = total.line !== null;
    }
  }
  const reasons = explain(e, home, away, soccer);
  const model = rows[0];
  const footnote = showTotalsCaveat
    ? "Probabilities, not promises. Back-tested against the closing line; see the models page. On totals the line is still the sharper number, so read a gap as disagreement, not an edge."
    : "Probabilities, not promises. Back-tested against the closing line; see the models page.";

  return (
    <section className="mt-4 rounded-md border-2 border-pitch/60 bg-surface p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="display text-xl font-extrabold">Who gets the W</h2>
        <span className="label text-[11px] text-muted">
          {model.modelName} {model.modelVersion}
        </span>
      </div>
      {bar}
      {details.length ? (
        <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {details.map((d) => (
            <div key={d.label} className="rounded-md bg-surface-2/60 px-3 py-2">
              <dt className="label text-[11px] text-muted">{d.label}</dt>
              <dd className="display tnum text-xl font-extrabold leading-tight">{d.value}</dd>
              {d.sub ? <dd className="tnum text-xs text-ink-2">{d.sub}</dd> : null}
            </div>
          ))}
        </dl>
      ) : null}
      {reasons.length ? (
        <ul className="mt-3 grid gap-1 text-sm text-ink-2">
          {reasons.map((r) => (
            <li key={r} className="flex gap-2">
              <span aria-hidden="true" className="text-pitch">▸</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-3 text-xs text-muted">{footnote}</p>
    </section>
  );
}
