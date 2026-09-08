import Link from "next/link";
import { NavLinks } from "./nav-links";

export function Nav() {
  return (
    <>
      <header className="sticky top-0 z-20 border-b border-line bg-ground/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-3 py-2 sm:px-5">
          <Link href="/" className="flex items-center gap-2" aria-label="Gimme a W home">
            <img src="/mark.svg" alt="" width={48} height={30} className="h-7 w-auto" />
            <span className="display text-2xl font-extrabold leading-none">
              Gimme a <span className="text-pitch">W</span>
            </span>
          </Link>
          <nav className="ml-auto hidden md:block">
            <NavLinks variant="top" />
          </nav>
          <Link
            href="/search"
            className="label ml-auto rounded border border-line-strong px-2 py-1 text-xs text-ink-2 md:ml-3"
          >
            Search
          </Link>
        </div>
      </header>
      <nav
        aria-label="Sections"
        className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <NavLinks variant="bottom" />
      </nav>
    </>
  );
}
