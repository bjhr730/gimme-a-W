# web

Next.js 15 app (App Router, Tailwind v4, server components). Mobile-first: bottom tab bar on
phones, top nav from 768px. Installable as a PWA.

## Routes

| Route | What |
|---|---|
| `/` | Today's games across all sports, with a date strip |
| `/soccer`, `/nfl`, `/cfb` | Same, scoped to one sport, plus links to every table |
| `/games/[id]` | Score, status, venue, weather, box-score stats, latest bookmaker lines |
| `/teams/[id]` | Elo, last-5 form, table positions, upcoming games, recent results, roster |
| `/players/[id]` | Player card and game log (passing/rushing/receiving or goals/shots per game) |
| `/standings/[slug]` | Latest table snapshot, grouped by conference/division when present |
| `/search?q=` | Team and player search |

Game pages also show per-player box scores (football) or lineups with goals and shots
(soccer), plus ESPN FPI picks when ESPN publishes one.

## Run

```bash
pnpm install
pnpm --filter web icons   # once: rasterize the logo mark into PWA icons
pnpm --filter web dev     # http://localhost:3000
```

Reads `DATABASE_URL` from the repo-root `.env` through `@gimme/db`. Pages revalidate every
1–5 minutes; the search page is dynamic.
