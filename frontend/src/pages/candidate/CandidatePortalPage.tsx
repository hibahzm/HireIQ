import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  type CandidateApplication,
  type CandidateProfile,
  type Invitation,
  type OpenJob,
} from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import Logo from "../../components/ui/Logo";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import Badge from "../../components/ui/Badge";
import { statusColor } from "../../components/ui/status";
import { BriefcaseIcon, LogOutIcon } from "../../components/ui/icons";

type Tab = "jobs" | "invitations" | "applications" | "profile";
type Notify = (b: { kind: "ok" | "err"; text: string }) => void;

const TABS: [Tab, string][] = [
  ["jobs", "Browse jobs"],
  ["invitations", "Invitations"],
  ["applications", "My applications"],
  ["profile", "My CV & profile"],
];

export default function CandidatePortalPage() {
  const { token, logout } = useAuth();
  const t = token ?? "";
  const [tab, setTab] = useState<Tab>("jobs");
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [banner, setBanner] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const loadProfile = useCallback(async () => {
    try {
      setProfile(await api.candidateAuth.me(t));
    } catch {
      /* identity chip stays empty */
    }
  }, [t]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  // Auto-dismiss the banner so it doesn't linger across tab switches.
  useEffect(() => {
    if (!banner) return;
    const id = setTimeout(() => setBanner(null), 4000);
    return () => clearTimeout(id);
  }, [banner]);

  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-20 border-b border-primary-100 bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3 sm:px-6">
          <Logo size={30} />
          <div className="flex items-center gap-3">
            {profile && (
              <span className="hidden text-sm text-primary-500 sm:inline">{profile.email}</span>
            )}
            <Button size="sm" variant="secondary" onClick={() => void logout()}>
              <LogOutIcon className="h-4 w-4" /> Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-primary-900">
              Welcome{profile?.full_name ? `, ${profile.full_name}` : ""}
            </h1>
            <p className="mt-1 text-sm text-primary-500">
              Manage your CV, browse open roles, and apply in one click.
            </p>
          </div>
          {profile && (
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                profile.open_to_work
                  ? "bg-green-100 text-green-800"
                  : "bg-primary-100 text-primary-500"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  profile.open_to_work ? "bg-green-500" : "bg-primary-400"
                }`}
              />
              {profile.open_to_work ? "Open to work" : "Not discoverable"}
            </span>
          )}
        </div>

        {banner && (
          <div
            role="status"
            className={`mt-4 rounded-lg px-4 py-2.5 text-sm ${
              banner.kind === "ok" ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"
            }`}
          >
            {banner.text}
          </div>
        )}

        <nav
          className="mt-6 flex flex-wrap gap-1 rounded-xl bg-primary-50 p-1 ring-1 ring-primary-100"
          role="tablist"
          aria-label="Candidate sections"
        >
          {TABS.map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50 ${
                tab === key
                  ? "bg-white text-brand-700 shadow-sm ring-1 ring-primary-100"
                  : "text-primary-500 hover:text-primary-700"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="mt-6">
          {tab === "jobs" && <BrowseJobs token={t} hasCv={!!profile?.has_cv} onNotify={setBanner} />}
          {tab === "invitations" && <Invitations token={t} onNotify={setBanner} />}
          {tab === "applications" && <MyApplications token={t} />}
          {tab === "profile" && (
            <ProfileTab token={t} profile={profile} onChanged={loadProfile} onNotify={setBanner} />
          )}
        </div>
      </main>
    </div>
  );
}

function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <Card className="p-10 text-center">
      <BriefcaseIcon className="mx-auto h-8 w-8 text-primary-300" />
      <p className="mt-3 text-sm font-medium text-primary-700">{title}</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-primary-500">{hint}</p>
    </Card>
  );
}

function BrowseJobs({ token, hasCv, onNotify }: { token: string; hasCv: boolean; onNotify: Notify }) {
  const [jobs, setJobs] = useState<OpenJob[] | null>(null);
  const [applying, setApplying] = useState<string | null>(null);

  const load = useCallback(async () => {
    setJobs(await api.candidate.browseJobs(token));
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function apply(jobId: string) {
    setApplying(jobId);
    try {
      await api.candidate.apply(token, jobId);
      onNotify({ kind: "ok", text: "Application submitted." });
      await load();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Could not apply" });
    } finally {
      setApplying(null);
    }
  }

  if (!jobs) return <Spinner label="Loading open roles…" />;
  if (jobs.length === 0)
    return <EmptyState title="No open roles right now" hint="New roles will appear here as companies post them." />;

  return (
    <div className="space-y-4">
      {!hasCv && (
        <div className="rounded-lg bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          Upload a CV in <span className="font-medium">My CV &amp; profile</span> before you can apply.
        </div>
      )}
      <ul className="space-y-3">
        {jobs.map((job) => (
          <li key={job.id}>
            <Card className="flex items-start justify-between gap-4 p-5">
              <div className="min-w-0">
                <h3 className="font-semibold text-primary-900">{job.title}</h3>
                {job.company_name && (
                  <p className="mt-0.5 text-sm text-primary-500">{job.company_name}</p>
                )}
                {job.description && (
                  <p className="mt-2 line-clamp-2 text-sm text-primary-600">{job.description}</p>
                )}
              </div>
              <Button
                size="sm"
                disabled={!hasCv || job.already_applied}
                loading={applying === job.id}
                onClick={() => apply(job.id)}
                className="shrink-0"
              >
                {job.already_applied ? "Applied" : "Apply"}
              </Button>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Invitations({ token, onNotify }: { token: string; onNotify: Notify }) {
  const [invites, setInvites] = useState<Invitation[] | null>(null);
  const [accepting, setAccepting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setInvites(await api.candidate.invitations(token));
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function accept(id: string) {
    setAccepting(id);
    try {
      await api.candidate.acceptInvitation(token, id);
      onNotify({ kind: "ok", text: "Invitation accepted — your application was submitted." });
      await load();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Could not accept" });
    } finally {
      setAccepting(null);
    }
  }

  if (!invites) return <Spinner label="Loading invitations…" />;
  if (invites.length === 0)
    return (
      <EmptyState
        title="No invitations yet"
        hint="When a company sources you for a role, their invitation shows up here."
      />
    );

  return (
    <ul className="space-y-3">
      {invites.map((inv) => (
        <li key={inv.id}>
          <Card className="flex items-start justify-between gap-4 p-5">
            <div className="min-w-0">
              <h3 className="font-semibold text-primary-900">{inv.job_title ?? "Role"}</h3>
              {inv.company_name && (
                <p className="mt-0.5 text-sm text-primary-500">{inv.company_name}</p>
              )}
              {inv.message && <p className="mt-2 text-sm text-primary-600">{inv.message}</p>}
            </div>
            {inv.status === "pending" ? (
              <Button
                size="sm"
                loading={accepting === inv.id}
                onClick={() => accept(inv.id)}
                className="shrink-0"
              >
                Accept &amp; apply
              </Button>
            ) : (
              <Badge status={inv.status} />
            )}
          </Card>
        </li>
      ))}
    </ul>
  );
}

function MyApplications({ token }: { token: string }) {
  const [apps, setApps] = useState<CandidateApplication[] | null>(null);

  useEffect(() => {
    void api.candidate.myApplications(token).then(setApps);
  }, [token]);

  if (!apps) return <Spinner label="Loading applications…" />;
  if (apps.length === 0)
    return (
      <EmptyState
        title="No applications yet"
        hint="Roles you apply to — directly or by accepting an invitation — appear here."
      />
    );

  return (
    <ul className="space-y-3">
      {apps.map((a) => (
        <li key={a.id}>
          <Card className="flex items-center justify-between gap-4 p-5">
            <div className="min-w-0">
              <h3 className="font-semibold text-primary-900">{a.job_title ?? "Role"}</h3>
              {a.company_name && (
                <p className="mt-0.5 text-sm text-primary-500">{a.company_name}</p>
              )}
            </div>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(
                a.screening_status
              )}`}
            >
              {a.screening_status === "pending" ? "Under review" : a.screening_status}
            </span>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function ProfileTab({
  token,
  profile,
  onChanged,
  onNotify,
}: {
  token: string;
  profile: CandidateProfile | null;
  onChanged: () => Promise<void>;
  onNotify: Notify;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const [savingToggle, setSavingToggle] = useState(false);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const cv = await api.candidate.uploadCv(token, file);
      setTruncated(cv.embedding_truncated);
      onNotify({ kind: "ok", text: "CV saved." });
      await onChanged();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Upload failed" });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function toggleOpenToWork(next: boolean) {
    setSavingToggle(true);
    try {
      await api.candidateAuth.updateProfile(token, { open_to_work: next });
      onNotify({
        kind: "ok",
        text: next ? "You're now discoverable by companies." : "You're hidden from company search.",
      });
      await onChanged();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Update failed" });
    } finally {
      setSavingToggle(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-semibold text-primary-900">Your CV</h3>
            <p className="mt-1 text-sm text-primary-500">
              {profile?.has_cv
                ? "A CV is on file. Uploading a new one replaces it everywhere — applications and sourcing."
                : "Upload your CV to apply to roles and be discovered by companies."}
            </p>
          </div>
          {profile?.has_cv && <Badge status="qualified">On file</Badge>}
        </div>
        {truncated && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Your CV was long — we indexed your most recent experience for search.
          </p>
        )}
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,image/jpeg,image/png"
          onChange={onFile}
          className="hidden"
        />
        <div className="mt-4 flex items-center gap-3">
          <Button size="sm" loading={uploading} onClick={() => fileRef.current?.click()}>
            {profile?.has_cv ? "Replace CV" : "Upload CV"}
          </Button>
          <span className="text-xs text-primary-400">PDF, DOCX, JPG or PNG · up to 10 MB</span>
        </div>
      </Card>

      <Card className="flex items-center justify-between gap-4 p-6">
        <div>
          <h3 className="font-semibold text-primary-900">Open to work</h3>
          <p className="mt-1 max-w-md text-sm text-primary-500">
            When on, companies sourcing for roles can discover your profile. Your contact details
            stay private until you accept an invitation.
          </p>
        </div>
        <button
          role="switch"
          aria-checked={!!profile?.open_to_work}
          aria-label="Toggle open to work"
          disabled={savingToggle}
          onClick={() => toggleOpenToWork(!profile?.open_to_work)}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50 disabled:opacity-60 ${
            profile?.open_to_work ? "bg-brand-600" : "bg-primary-300"
          }`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200 ${
              profile?.open_to_work ? "translate-x-[22px]" : "translate-x-0.5"
            }`}
          />
        </button>
      </Card>
    </div>
  );
}
