interface Props {
  label?: string;
  className?: string;
}

export default function Spinner({ label, className = "" }: Props) {
  return (
    <div className={`flex flex-col items-center gap-3 text-primary-400 ${className}`}>
      <svg
        className="h-7 w-7 animate-spin text-brand-600"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-90"
          fill="currentColor"
          d="M4 12a8 8 0 0 1 8-8V0C5.4 0 0 5.4 0 12h4z"
        />
      </svg>
      {label ? <p className="text-sm" role="status">{label}</p> : null}
    </div>
  );
}
