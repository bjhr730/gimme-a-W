import Link from "next/link";
import { PageTitle } from "@/components/page-title";
import { latestScorecard, modelRuns } from "@/lib/queries";

export const revalidate = 600;
export const metadata = { title: "Models" };

type Season = { season: string; games: number } & Record<string, number | string>;
type Metrics = {
  competition?: string;
  train_games?: number;
  seasons?: Season[];
  overall?: Record<string, number>;
  // how the injury report changed a props run
  players_withheld_unavailable?: number;
  players_flagged_doubtful?: number;
};

function num(v: unknown, digits = 4): string {
  return typeof v === "number" ? v.toFixed(digits) : "–";
}

function pctDiff(model: unknown, market: unknown): string {
  if (typeof model !== "number" || typeof market !== "number" || market === 0) return "";
  const d = ((model - market) / market) * 100;
  return `${d > 0 ? "+" : ""}${d.toFixed(1)}% vs market`;
}

type Scorecard = {
  window_days: number;
  games: number;
  competitions: Record<string, { games: number; log_loss: number; accuracy: number; market_log_loss?: number; log_loss_on_market_games?: number; market_games?: number }>;
};

export default async function ModelsPage() {
  const [runs, scorecard] = await Promise.all([modelRuns(), latestScorecard()]);
  const order = ["nfl", "college-football"];
  const rank = (r: (typeof runs)[number]) => {
    const slug = (r.metrics as Metrics).competition ?? r.notes ?? "";
    const i = order.indexOf(slug);
    return i === -1 ? `1-${slug}` : `0-${i}`;
  };
  const backtests = runs
    .filter((r) => (r.metrics as Metrics).seasons && r.modelName !== "scorecard")
    .sort((a, b) => rank(a).localeCompare(rank(b)));
  const live = runs.filter((r) => !(r.metrics as Metrics).seasons && r.modelName !== "scorecard");
  const card = (scorecard?.metrics ?? null) as Scorecard | null;
  return (
    <>
      <PageTitle
        eyebrow="Prediction engine"
        title="Models"
        aside={<Link href="/status" className="label text-xs text-pitch">System status →</Link>}
      />
      <p className="mb-6 max-w-[70ch] text-ink-2">
        Every model is trained only on games played before the one it predicts, then scored
        season by season against the bookmaker&apos;s closing line. Log loss is the headline
        number: lower is better, and the market is the bar to clear. Published probabilities
        blend the model with the market when a line exists.
      </p>

      {card && card.games === 0 ? (
        <section className="mb-6 rounded-md border border-dashed border-line-strong bg-surface px-4 py-3">
          <h2 className="display text-xl font-extrabold">Live scorecard</h2>
          <p className="mt-1 max-w-[70ch] text-sm text-ink-2">
            Nothing graded yet. This scores what the site actually published before kickoff,
            so it fills in only once games that were predicted in advance finish. The engine
            started publishing today, which means the first entries arrive with this week&apos;s
            results. The back-tests below already cover past seasons.
          </p>
        </section>
      ) : null}

      {card && card.games > 0 ? (
        <section className="mb-6 rounded-md border-2 border-pitch/60 bg-surface">
          <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-3 py-2">
            <h2 className="display text-xl font-extrabold">Live scorecard · last {card.window_days} days</h2>
            <span className="label text-[11px] text-muted">{card.games} graded games · what the site actually published before kickoff</span>
          </header>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b border-line">
                  <th className="label px-3 py-1.5 text-left text-[11px] text-muted">Competition</th>
                  <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Games</th>
                  <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Our log loss</th>
                  <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Market</th>
                  <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Accuracy</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(card.competitions)
                  .sort((a, b) => b[1].games - a[1].games)
                  .map(([slug, m]) => (
                    <tr key={slug} className="border-b border-line last:border-b-0">
                      <td className="px-3 py-1.5">{slug}</td>
                      <td className="tnum px-2 py-1.5 text-right">{m.games}</td>
                      <td className="tnum px-2 py-1.5 text-right">{m.log_loss.toFixed(4)}</td>
                      <td className="tnum px-2 py-1.5 text-right text-ink-2">
                        {m.market_log_loss !== undefined ? `${m.market_log_loss.toFixed(4)} (ours ${m.log_loss_on_market_games?.toFixed(4)})` : "no line"}
                      </td>
                      <td className="tnum px-2 py-1.5 text-right">{Math.round(m.accuracy * 100)}%</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {backtests.length === 0 ? (
        <p className="text-ink-2">No back-tests recorded yet.</p>
      ) : (
        backtests.map((r) => {
          const m = r.metrics as Metrics;
          const o = m.overall ?? {};
          const soccer = r.sportId === "soccer";
          return (
            <section key={r.id} className="mb-6 rounded-md border border-line bg-surface">
              <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-3 py-2">
                <h2 className="display text-xl font-extrabold">
                  {m.competition ?? r.notes} · {r.modelName} {r.modelVersion}
                </h2>
                <span className="label text-[11px] text-muted">
                  {m.seasons?.length} seasons · {o.games} games · run {r.startedAt.toISOString().slice(0, 10)}
                </span>
              </header>
              <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-4">
                <div className="rounded-md bg-surface-2/60 px-3 py-2">
                  <p className="label text-[11px] text-muted">Model log loss</p>
                  <p className="display tnum text-2xl font-extrabold leading-tight">{num(o.model_log_loss)}</p>
                  <p className="tnum text-xs text-ink-2">{pctDiff(o.model_log_loss_on_market_games ?? o.model_log_loss, o.market_log_loss)}</p>
                </div>
                <div className="rounded-md bg-surface-2/60 px-3 py-2">
                  <p className="label text-[11px] text-muted">Blend log loss</p>
                  <p className="display tnum text-2xl font-extrabold leading-tight">{num(o.blend_log_loss_on_market_games ?? o.blend_log_loss)}</p>
                  <p className="tnum text-xs text-ink-2">{pctDiff(o.blend_log_loss_on_market_games ?? o.blend_log_loss, o.market_log_loss)}</p>
                </div>
                <div className="rounded-md bg-surface-2/60 px-3 py-2">
                  <p className="label text-[11px] text-muted">Market log loss</p>
                  <p className="display tnum text-2xl font-extrabold leading-tight">{num(o.market_log_loss)}</p>
                  <p className="tnum text-xs text-ink-2">closing line, the bar</p>
                </div>
                <div className="rounded-md bg-surface-2/60 px-3 py-2">
                  <p className="label text-[11px] text-muted">{soccer ? "Total goals MAE" : "Spread MAE"}</p>
                  <p className="display tnum text-2xl font-extrabold leading-tight">
                    {num(soccer ? o.total_goals_mae_model : o.spread_mae_model, 2)}
                  </p>
                  <p className="tnum text-xs text-ink-2">
                    {soccer ? "" : `market ${num(o.spread_mae_market, 2)}`}
                  </p>
                </div>
              </div>
              <div className="overflow-x-auto border-t border-line">
                <table className="w-full min-w-[520px] text-sm">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="label px-3 py-1.5 text-left text-[11px] text-muted">Season</th>
                      <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Games</th>
                      <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Model</th>
                      <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Blend</th>
                      <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Market</th>
                      <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Accuracy</th>
                      {soccer ? null : (
                        <>
                          <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Spread MAE</th>
                          <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Total MAE</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {(m.seasons ?? []).map((s) => (
                      <tr key={s.season} className="border-b border-line last:border-b-0">
                        <td className="px-3 py-1.5">{s.season}</td>
                        <td className="tnum px-2 py-1.5 text-right">{s.games}</td>
                        <td className="tnum px-2 py-1.5 text-right">{num(s.model_log_loss_on_market_games ?? s.model_log_loss)}</td>
                        <td className="tnum px-2 py-1.5 text-right">{num(s.blend_log_loss_on_market_games ?? s.blend_log_loss)}</td>
                        <td className="tnum px-2 py-1.5 text-right">{num(s.market_log_loss)}</td>
                        <td className="tnum px-2 py-1.5 text-right">
                          {typeof s.model_accuracy === "number" ? `${(s.model_accuracy * 100).toFixed(0)}%` : "–"}
                          {typeof s.market_accuracy === "number" ? ` / ${(s.market_accuracy * 100).toFixed(0)}%` : ""}
                        </td>
                        {soccer ? null : (
                          <>
                            <td className="tnum px-2 py-1.5 text-right">{num(s.spread_mae_model, 2)} / {num(s.spread_mae_market, 2)}</td>
                            <td className="tnum px-2 py-1.5 text-right">{num(s.total_mae_model, 2)} / {num(s.total_mae_market, 2)}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })
      )}

      {live.length ? (
        <section className="rounded-md border border-line bg-surface">
          <h2 className="label border-b border-line px-3 py-1.5 text-xs text-ink-2">Latest prediction runs</h2>
          <ul className="divide-y divide-line">
            {live.map((r) => {
              const m = r.metrics as Metrics;
              return (
                <li key={r.id} className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-2 text-sm">
                  <span>
                    <span className="font-semibold">{m.competition ?? r.notes}</span>
                    <span className="text-muted"> · {r.modelName} {r.modelVersion}</span>
                  </span>
                  <span className="tnum text-ink-2">
                    {r.snapshotCount} games · trained on {m.train_games ?? "–"}
                    {m.players_withheld_unavailable
                      ? ` · ${m.players_withheld_unavailable} held out injured`
                      : ""}
                    {m.players_flagged_doubtful ? ` · ${m.players_flagged_doubtful} doubtful` : ""}
                    {" · "}
                    {r.startedAt.toISOString().slice(0, 16).replace("T", " ")} UTC
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </>
  );
}
