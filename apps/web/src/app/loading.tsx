export default function Loading() {
  return (
    <div aria-busy="true" aria-live="polite" className="grid gap-3">
      <div className="h-8 w-48 animate-pulse rounded bg-surface-2" />
      <div className="h-14 w-full animate-pulse rounded-md bg-surface-2" />
      <div className="h-40 w-full animate-pulse rounded-md bg-surface-2" />
      <div className="h-40 w-full animate-pulse rounded-md bg-surface-2" />
      <span className="sr-only">Loading</span>
    </div>
  );
}
