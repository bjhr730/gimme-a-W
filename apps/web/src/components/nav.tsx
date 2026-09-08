import Link from "next/link";
import { BackButton } from "./back-button";
import { NavLinks } from "./nav-links";
import { SearchBox } from "./search-box";
import { ThemeToggle } from "./theme-toggle";

export function Nav() {
  return (
    <>
      <header className="sticky top-0 z-20 border-b border-line bg-ground/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-2 px-3 py-2 sm:gap-3 sm:px-5">
          <BackButton />
          <Link href="/" className="flex min-w-0 items-center gap-2" aria-label="Gimme a W home">
            <img src="/mark.svg" alt="" width={48} height={30} className="h-7 w-auto" />
            <span className="display truncate text-xl font-extrabold leading-none sm:text-2xl">
              Gimme a <span className="text-pitch">W</span>
            </span>
          </Link>
          <nav className="ml-auto hidden md:block">
            <NavLinks variant="top" />
          </nav>
          <div className="ml-auto flex items-center gap-2 md:ml-3">
            <ThemeToggle />
            <SearchBox variant="header" />
          </div>
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
