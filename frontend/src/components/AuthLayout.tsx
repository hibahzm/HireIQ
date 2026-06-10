interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

/** Centered branded card for signed-out pages (login / register / set-password). */
export default function AuthLayout({ title, subtitle, children, footer }: Props) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas px-4 py-10">
      <div className="mb-6 flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-base font-extrabold text-white">
          H
        </span>
        <span className="text-xl font-extrabold tracking-tight text-primary-800">HireIQ</span>
      </div>
      <div className="w-full max-w-md rounded-xl border border-primary-100 bg-surface p-8 shadow-card">
        <h1 className="text-xl font-bold text-primary-800">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-primary-500">{subtitle}</p>}
        <div className="mt-6">{children}</div>
      </div>
      {footer && <div className="mt-4 text-sm text-primary-500">{footer}</div>}
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
