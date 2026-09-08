import { PageTitle } from "@/components/page-title";
import { LocalTime } from "@/components/local-time";
import { statusSnapshot } from "@/lib/queries";

export const revalidate = 120;
export const metadata = { title: "Status" };

function ago(d: Date | null): string {
  if (!d) return "never";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export default async function StatusPage() {
  const s = await statusSnapshot();
  const failed = s.collectorRuns.filter((r) => r.status === "failed").length;
  const stale = !s.lastGameUpdate || Date.now() - s.lastGameUpdate.getTime() > 36 * 3600 * 1000;
  const healthy = failed === 0 && !stale;
  return (
    <>
      <PageTitle
        eyebrow="Production"
        title="System status"
        aside={
          <span className={`label rounded px-2 py-1 text-xs ${healthy ? "bg-pitch-soft text-pitch" : "bg-leather-soft text-leather"}`}>
            {healthy ? "Healthy" : "Needs attention"}
          </span>
        }
      />

      <section className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ["Last data update", ago(s.lastGameUpdate)],
          ["Last prediction", ago(s.lastPrediction)],
          ["Games", s.counts.games.toLocaleString("en-US")],
          ["Predictions", s.counts.predictions.toLocaleString("en-US")],
        ].map(([k, v]) => (
          <div key={k} className="rounded-md border border-line bg-surface px-3 py-2">
            <p className="label text-[11px] text-muted">{k}</p>
            <p className="display tnum text-2xl font-extrabold leading-tight">{v}</p>
          </div>
        ))}
      </section>

      <section className="mb-6 rounded-md border border-line bg-surface">
        <h2 className="label border-b border-line px-3 py-1.5 text-xs text-ink-2">Data freshness by competition</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className="label px-3 py-1.5 text-left text-[11px] text-muted">Competition</th>
                <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Games</th>
                <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Latest final</th>
                <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Next 7 days</th>
                <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Predicted</th>
              </tr>
            </thead>
            <tbody>
              {s.freshness.map((f) => (
                <tr key={f.slug} className="border-b border-line last:border-b-0">
                  <td className="px-3 py-1.5">{f.name}</td>
                  <td className="tnum px-2 py-1.5 text-right">{f.games.toLocaleString("en-US")}</td>
                  <td className="tnum px-2 py-1.5 text-right text-ink-2">{f.lastFinal ? f.lastFinal.toISOString().slice(0, 10) : "–"}</td>
                  <td className="tnum px-2 py-1.5 text-right">{f.upcoming}</td>
                  <td className={`tnum px-2 py-1.5 text-right ${f.upcoming > 0 && f.predicted < f.upcoming ? "text-leather" : ""}`}>
                    {f.upcoming > 0 ? `${f.predicted}/${f.upcoming}` : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mb-6 rounded-md border border-line bg-surface">
        <h2 className="label border-b border-line px-3 py-1.5 text-xs text-ink-2">Collector runs, most recent first</h2>
        <ul className="divide-y divide-line">
          {s.collectorRuns.map((r) => (
            <li key={r.id} className="grid grid-cols-[auto_1fr_auto] items-baseline gap-3 px-3 py-1.5 text-sm">
              <span className={`label text-[10px] ${r.status === "failed" ? "text-leather" : r.status === "running" ? "text-muted" : "text-pitch"}`}>{r.status}</span>
              <span className="min-w-0">
                <span className="font-semibold">{r.source}</span>
                <span className="text-muted"> · {r.adapter}</span>
                {r.error ? <span className="block truncate text-xs text-leather">{r.error.split("\n")[0]}</span> : null}
              </span>
              <span className="tnum text-right text-xs text-ink-2">
                {r.rowsWritten.toLocaleString("en-US")} rows · <LocalTime iso={r.startedAt.toISOString()} mode="datetime" />
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-md border border-line bg-surface">
        <h2 className="label border-b border-line px-3 py-1.5 text-xs text-ink-2">Model runs, most recent first</h2>
        <ul className="divide-y divide-line">
          {s.modelRuns.map((r) => (
            <li key={r.id} className="grid grid-cols-[1fr_auto] items-baseline gap-3 px-3 py-1.5 text-sm">
              <span>
                <span className="font-semibold">{r.modelName}</span>
                <span className="text-muted"> {r.modelVersion} · {r.notes ?? ""}</span>
              </span>
              <span className="tnum text-right text-xs text-ink-2">
                {r.snapshotCount ?? 0} · <LocalTime iso={r.startedAt.toISOString()} mode="datetime" />
              </span>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
