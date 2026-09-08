"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="py-16 text-center">
      <p className="display text-6xl font-extrabold text-line-strong">L</p>
      <h1 className="display mt-2 text-2xl font-extrabold">Something broke on this page</h1>
      <p className="mx-auto mt-1 max-w-[50ch] text-ink-2">
        Usually a slow database connection. Try again in a moment; if it keeps happening the
        status page will show what is going on.
      </p>
      {error.digest ? <p className="tnum mt-1 text-xs text-muted">ref {error.digest}</p> : null}
      <div className="mt-4 flex justify-center gap-2">
        <button type="button" onClick={reset} className="label rounded-md bg-pitch px-4 py-2 text-sm text-white">
          Try again
        </button>
        <Link href="/status" className="label rounded-md border border-line-strong px-4 py-2 text-sm text-ink-2">
          Status
        </Link>
      </div>
    </div>
  );
}
