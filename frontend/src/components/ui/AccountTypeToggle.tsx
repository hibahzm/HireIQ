export type AccountType = "company" | "candidate";

interface Props {
  value: AccountType;
  onChange: (value: AccountType) => void;
}

const OPTIONS: { value: AccountType; label: string; hint: string }[] = [
  { value: "company", label: "I'm hiring", hint: "Company" },
  { value: "candidate", label: "I'm looking for a job", hint: "Candidate" },
];

/** Segmented control: choose whether you're signing in as a company or a candidate. */
export default function AccountTypeToggle({ value, onChange }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Account type"
      className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1"
    >
      {OPTIONS.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={[
              "rounded-lg px-3 py-2 text-sm font-medium transition-colors cursor-pointer",
              active
                ? "bg-white text-brand-700 shadow-sm"
                : "text-slate-500 hover:text-slate-700",
            ].join(" ")}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
