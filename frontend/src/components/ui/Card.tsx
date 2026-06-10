interface Props extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export default function Card({ children, className = "", ...props }: Props) {
  return (
    <div
      className={`rounded-xl border border-primary-100 bg-surface shadow-card ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
