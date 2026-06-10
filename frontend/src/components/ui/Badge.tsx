import { statusColor, statusLabel } from "./status";

interface Props {
  status?: string;
  className?: string;
  children?: React.ReactNode;
}

/**
 * Status pill. Pass a known `status` to get its centralized label + color,
 * or pass `children` + `className` for a custom badge.
 */
export default function Badge({ status, className, children }: Props) {
  const classes = className ?? (status ? statusColor(status) : "bg-primary-100 text-primary-600");
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${classes}`}
    >
      {children ?? (status ? statusLabel(status) : null)}
    </span>
  );
}
