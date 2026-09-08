import Link from "next/link";
import { addDays, weekdayLabel } from "@/lib/format";

export function DateStrip({
  base,
  selected,
  today,
  withGames,
  range = 3,
}: {
  base: string; // path without query, e.g. "/soccer"
  selected: string;
  today: string;
  withGames: Set<string>;
  range?: number;
}) {
  const days = Array.from({ length: range * 2 + 1 }, (_, i) => addDays(selected, i - range));
  return (
    <nav aria-label="Pick a day" className="no-scrollbar -mx-3 overflow-x-auto px-3 sm:mx-0 sm:px-0">
      <ul className="flex min-w-max gap-1">
        {days.map((day) => {
          const { top, bottom } = weekdayLabel(day, today);
          const active = day === selected;
          const has = withGames.has(day);
          return (
            <li key={day}>
              <Link
                href={day === today ? base : `${base}?date=${day}`}
                aria-current={active ? "date" : undefined}
                className={`flex w-14 flex-col items-center rounded-md border px-1 py-1.5 ${
                  active
                    ? "border-pitch bg-pitch text-white"
                    : "border-line bg-surface text-ink-2 hover:border-line-strong"
                }`}
              >
                <span className="label text-[10px]">{top}</span>
                <span className="display tnum text-lg font-extrabold leading-tight">{bottom}</span>
                <span
                  aria-hidden="true"
                  className={`mt-0.5 h-1 w-1 rounded-full ${
                    has ? (active ? "bg-white" : "bg-pitch") : "bg-transparent"
                  }`}
                />
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
