interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

import Logo from "./ui/Logo";

/** Centered branded card for signed-out pages (login / register / set-password). */
export default function AuthLayout({ title, subtitle, children, footer }: Props) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-canvas px-4 py-10">
      {/* Ambient brand glow behind the card */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-32 left-1/2 h-96 w-[36rem] -translate-x-1/2 rounded-full bg-brand-200/40 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-40 right-[-10rem] h-80 w-80 rounded-full bg-brand-100/60 blur-3xl"
      />

      <div className="relative mb-6 animate-fade-in-up">
        <Logo size={44} animated />
      </div>
      <div
        className="relative w-full max-w-md animate-fade-in-up rounded-xl border border-primary-100 bg-surface/95 p-8 shadow-card backdrop-blur"
        style={{ animationDelay: "120ms" }}
      >
        <h1 className="text-xl font-bold text-primary-800">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-primary-500">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
      {footer && (
        <div className="relative mt-4 animate-fade-in text-sm text-primary-500" style={{ animationDelay: "300ms" }}>
          {footer}
        </div>
      )}
    </div>
  );
}

const inputClass =
  "mt-1 block w-full rounded-lg border border-primary-200 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30";

export function Field({
  id,
  label,
  ...props
}: { id: string; label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-primary-700">
        {label}
      </label>
      <input id={id} className={inputClass} {...props} />
    </div>
  );
}
