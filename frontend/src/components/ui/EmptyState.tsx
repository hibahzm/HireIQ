interface Props {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}

export default function EmptyState({ title, description, action, icon }: Props) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-primary-200 bg-surface px-6 py-14 text-center">
      {icon ? <div className="mb-3 text-primary-300">{icon}</div> : null}
      <h3 className="text-sm font-semibold text-primary-700">{title}</h3>
      {description ? (
        <p className="mt-1 max-w-sm text-sm text-primary-500">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
