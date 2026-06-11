interface Props extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  /** Lift the card on hover — use for clickable cards. */
  interactive?: boolean;
}

export default function Card({ children, interactive = false, className = "", ...props }: Props) {
  return (
    <div
      className={`rounded-xl border border-primary-100 bg-surface shadow-card ${
        interactive
          ? "cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-card-hover"
          : ""
      } ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
