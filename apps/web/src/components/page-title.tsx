export function PageTitle({
  eyebrow,
  title,
  aside,
}: {
  eyebrow?: string;
  title: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        {eyebrow ? <p className="label text-xs text-muted">{eyebrow}</p> : null}
        <h1 className="display text-3xl font-extrabold leading-none sm:text-4xl">{title}</h1>
      </div>
      {aside ? <div className="text-sm text-ink-2">{aside}</div> : null}
    </div>
  );
}
