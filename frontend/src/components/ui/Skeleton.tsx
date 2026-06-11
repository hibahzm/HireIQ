interface Props {
  className?: string;
}

/** Shimmering placeholder. Size it with width/height utility classes. */
export default function Skeleton({ className = "" }: Props) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/** Card-shaped skeleton matching the standard Card layout. */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-xl border border-primary-100 bg-surface p-5 shadow-card">
      <div className="skeleton h-5 w-2/5" />
      <div className="mt-4 space-y-2.5">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="skeleton h-3.5" style={{ width: `${90 - i * 15}%` }} />
        ))}
      </div>
    </div>
  );
}
