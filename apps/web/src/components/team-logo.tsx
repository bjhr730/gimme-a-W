export function TeamLogo({
  src,
  name,
  size = 28,
}: {
  src: string | null | undefined;
  name: string;
  size?: number;
}) {
  if (!src) {
    return (
      <span
        aria-hidden="true"
        className="label inline-flex shrink-0 items-center justify-center rounded-full bg-surface-2 text-[10px] text-ink-2"
        style={{ width: size, height: size }}
      >
        {name.slice(0, 2)}
      </span>
    );
  }
  return (
    // ESPN logos are already optimized PNGs; no need to route them through next/image.
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      className="shrink-0 object-contain"
      style={{ width: size, height: size }}
    />
  );
}
