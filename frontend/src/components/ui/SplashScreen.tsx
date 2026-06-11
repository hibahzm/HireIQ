import Logo from "./Logo";

interface Props {
  label?: string;
}

/** Full-screen branded loader shown while the app boots or a session restores. */
export default function SplashScreen({ label = "Loading…" }: Props) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas">
      <div className="animate-float">
        <Logo size={56} animated />
      </div>
      <div className="mt-8 flex items-center gap-1.5" role="status" aria-label={label}>
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="h-2 w-2 rounded-full bg-brand-500 animate-dot-bounce"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
      <p className="mt-3 text-sm text-primary-400 animate-fade-in" style={{ animationDelay: "400ms" }}>
        {label}
      </p>
    </div>
  );
}
