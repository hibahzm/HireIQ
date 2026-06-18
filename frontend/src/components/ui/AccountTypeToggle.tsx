export type AccountType = "company" | "candidate";

interface Props {
  value: AccountType;
  onChange: (value: AccountType) => void;
}

const OPTIONS: { value: AccountType; label: string; hint: string }[] = [
  { value: "company", label: "I'm hiring", hint: "Company" },
  { value: "candidate", label: "Looking for a job", hint: "Candidate" },
];

/** Segmented control: sign in as a company (hiring) or a candidate (job-seeking). */
export default function AccountTypeToggle({ value, onChange }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Account type"
      className="grid grid-cols-2 gap-1 rounded-xl bg-primary-50 p-1 ring-1 ring-primary-100"
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
            className={`flex flex-col items-center rounded-lg px-3 py-2 text-sm font-semibold transition-colors duration-150 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50 ${
              active
                ? "bg-white text-brand-700 shadow-sm ring-1 ring-primary-100"
                : "text-primary-500 hover:text-primary-700"
            }`}
          >
            <span>{opt.label}</span>
            <span
              className={`mt-0.5 text-[11px] font-medium ${
                active ? "text-brand-500" : "text-primary-400"
              }`}
            >
              {opt.hint}
            </span>
          </button>
        );
      })}
    </div>
  );
}
