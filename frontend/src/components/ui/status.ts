// Centralized status label + color maps (previously duplicated across pages).

export const STATUS_LABELS: Record<string, string> = {
  // application / screening
  pending: "Pending",
  qualified: "Qualified",
  rejected: "Rejected",
  screening: "Screening",
  failed: "Failed",
  system_interrupted: "Interrupted",
  abandoned: "Abandoned",
  invited: "Invited",
  interviewing: "Interviewing",
  evaluated: "Evaluated",
  // job
  draft: "Draft",
  setup: "Setup",
  setup_failed: "Setup failed",
  active: "Active",
  paused: "Paused",
  closed: "Closed",
  archived: "Archived",
};

export const STATUS_COLORS: Record<string, string> = {
  qualified: "bg-green-100 text-green-800",
  active: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-700",
  closed: "bg-red-100 text-red-700",
  pending: "bg-primary-100 text-primary-600",
  draft: "bg-primary-100 text-primary-600",
  screening: "bg-amber-100 text-amber-800",
  setup: "bg-amber-100 text-amber-800",
  setup_failed: "bg-red-100 text-red-700",
  failed: "bg-red-100 text-red-700",
  system_interrupted: "bg-orange-100 text-orange-800",
  paused: "bg-orange-100 text-orange-800",
  abandoned: "bg-primary-100 text-primary-400",
  invited: "bg-blue-100 text-blue-800",
  interviewing: "bg-purple-100 text-purple-800",
  evaluated: "bg-indigo-100 text-indigo-800",
  archived: "bg-primary-100 text-primary-400",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "bg-primary-100 text-primary-600";
}
