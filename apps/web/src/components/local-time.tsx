"use client";

import { useEffect, useState } from "react";

/**
 * Renders a kickoff in the viewer's time zone. The server renders UTC first so
 * the markup is deterministic; the client swaps in local time after mount.
 */
export function LocalTime({
  iso,
  mode = "time",
}: {
  iso: string;
  mode?: "time" | "datetime";
}) {
  const initial = format(iso, mode, "UTC");
  const [text, setText] = useState(initial);
  useEffect(() => {
    setText(format(iso, mode));
  }, [iso, mode]);
  return (
    <time dateTime={iso} suppressHydrationWarning className="tnum">
      {text}
    </time>
  );
}

function format(iso: string, mode: "time" | "datetime", timeZone?: string): string {
  const d = new Date(iso);
  if (mode === "time") {
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone });
  }
  return d.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });
}
