import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <p className="display text-6xl font-extrabold text-line-strong">L</p>
      <h1 className="display mt-2 text-2xl font-extrabold">Nothing here</h1>
      <p className="mt-1 text-ink-2">That page does not exist or has not been collected yet.</p>
      <Link href="/" className="label mt-4 inline-block rounded-md bg-pitch px-4 py-2 text-sm text-white">
        Back to today
      </Link>
    </div>
  );
}
