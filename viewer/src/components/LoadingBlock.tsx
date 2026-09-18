/** Lightweight loading placeholder — avoids blank screens without layout jump. */
export function LoadingBlock({
  label,
  lines = 3,
}: {
  label: string;
  lines?: number;
}) {
  return (
    <div role="status" aria-live="polite" className="space-y-3" aria-label={label}>
      <p className="text-sm text-[var(--color-muted)]">{label}</p>
      <div className="space-y-2" aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <div
            key={index}
            className="h-3 max-w-full rounded bg-[var(--color-line)]/80"
            style={{ width: `${88 - index * 12}%` }}
          />
        ))}
      </div>
    </div>
  );
}
