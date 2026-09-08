# web

Next.js 15 app (App Router, Tailwind v4, server components). Mobile-first: bottom tab bar on
phones, top nav from 768px. Installable as a PWA.

## Routes

| Route | What |
|---|---|
| `/` | Today's games across all sports, with a date strip |
| `/soccer`, `/nfl`, `/cfb` | Same, scoped to one sport, plus links to every table |
| `/games/[id]` | Score, status, venue, weather, box-score stats, latest bookmaker lines |
| `/teams/[id]` | Team position in its tables, upcoming games, recent results |
| `/standings/[slug]` | Latest table snapshot, grouped by conference/division when present |
| `/search?q=` | Team search |

Player pages arrive with roster collection in phase 3.

## Run

```bash
pnpm install
pnpm --filter web icons   # once: rasterize the logo mark into PWA icons
pnpm --filter web dev     # http://localhost:3000
```

Reads `DATABASE_URL` from the repo-root `.env` through `@gimme/db`. Pages revalidate every
1–5 minutes; the search page is dynamic.
