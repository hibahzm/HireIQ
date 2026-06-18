import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import Modal from "../../components/ui/Modal";
import EmptyState from "../../components/ui/EmptyState";
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

function interviewActive(a: CandidateApplication): boolean {
  if (!a.interview_token) return false;
  if (!a.interview_token_expires_at) return true;
  return new Date(a.interview_token_expires_at).getTime() > Date.now();
}

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

const briefcase = <BriefcaseIcon className="h-7 w-7" />;

function BrowseJobs({ token, hasCv, onNotify }: { token: string; hasCv: boolean; onNotify: Notify }) {
  const [jobs, setJobs] = useState<OpenJob[] | null>(null);
  const [query, setQuery] = useState("");
  const [applying, setApplying] = useState<string | null>(null);
  const [selected, setSelected] = useState<OpenJob | null>(null);

  const load = useCallback(async () => {
    setJobs(await api.candidate.browseJobs(token));
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    if (!jobs) return null;
    const q = query.trim().toLowerCase();
    if (!q) return jobs;
    return jobs.filter((j) =>
      [j.title, j.company_name, j.description]
        .filter(Boolean)
        .some((v) => (v as string).toLowerCase().includes(q))
    );
  }, [jobs, query]);

  async function apply(jobId: string) {
    setApplying(jobId);
    try {
      await api.candidate.apply(token, jobId);
      onNotify({ kind: "ok", text: "Application submitted." });
      setSelected(null);
      await load();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Could not apply" });
    } finally {
      setApplying(null);
    }
  }

  if (!jobs) return <Spinner label="Loading open roles…" />;

  return (
    <div className="space-y-4">
      {!hasCv && (
        <div className="rounded-lg bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          Upload a CV in <span className="font-medium">My CV &amp; profile</span> before you can apply.
        </div>
      )}

      <label className="relative block">
        <span className="sr-only">Search roles</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search roles by title, company, or keyword…"
          className="w-full rounded-lg border border-primary-200 bg-surface px-4 py-2.5 text-sm text-primary-800 placeholder:text-primary-400 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/30"
        />
      </label>

      {filtered && filtered.length === 0 ? (
        <EmptyState
          icon={briefcase}
          title={query ? "No roles match your search" : "No open roles right now"}
          description={
            query ? "Try a different keyword." : "New roles will appear here as companies post them."
          }
        />
      ) : (
        <ul className="space-y-3">
          {filtered?.map((job) => (
            <li key={job.id}>
              <Card interactive className="p-5" onClick={() => setSelected(job)}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-primary-900">{job.title}</h3>
                    {job.company_name && (
                      <p className="mt-0.5 text-sm text-primary-500">{job.company_name}</p>
                    )}
                    {job.description && (
                      <p className="mt-2 line-clamp-2 text-sm text-primary-600">{job.description}</p>
                    )}
                    <span className="mt-2 inline-block text-xs font-medium text-brand-600">
                      View details →
                    </span>
                  </div>
                  {job.already_applied && <Badge status="invited">Applied</Badge>}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.title}
        footer={
          selected && (
            <>
              <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
              <Button
                size="sm"
                disabled={!hasCv || selected.already_applied}
                loading={applying === selected.id}
                onClick={() => apply(selected.id)}
              >
                {selected.already_applied ? "Already applied" : "Apply now"}
              </Button>
            </>
          )
        }
      >
        {selected && (
          <div>
            {selected.company_name && (
              <p className="text-sm font-medium text-primary-500">{selected.company_name}</p>
            )}
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-primary-700">
              {selected.description || "No description provided."}
            </p>
            {!hasCv && (
              <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Upload a CV in your profile to apply.
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

function Invitations({ token, onNotify }: { token: string; onNotify: Notify }) {
  const [invites, setInvites] = useState<Invitation[] | null>(null);
  const [apps, setApps] = useState<CandidateApplication[] | null>(null);
  const [accepting, setAccepting] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [inv, ap] = await Promise.all([
      api.candidate.invitations(token),
      api.candidate.myApplications(token),
    ]);
    setInvites(inv);
    setApps(ap);
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

  if (!invites || !apps) return <Spinner label="Loading invitations…" />;

  const pendingSourcing = invites.filter((i) => i.status === "pending");
  const interviewReady = apps.filter(interviewActive);

  if (pendingSourcing.length === 0 && interviewReady.length === 0)
    return (
      <EmptyState
        icon={briefcase}
        title="No invitations yet"
        description="When a company invites you to apply, or you're invited to interview after applying, it shows up here."
      />
    );

  return (
    <div className="space-y-6">
      {interviewReady.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-primary-700">Interview invitations</h2>
          <ul className="space-y-3">
            {interviewReady.map((a) => (
              <li key={a.id}>
                <Card className="flex items-center justify-between gap-4 p-5">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-primary-900">{a.job_title ?? "Role"}</h3>
                    {a.company_name && (
                      <p className="mt-0.5 text-sm text-primary-500">{a.company_name}</p>
                    )}
                    <p className="mt-1 text-xs text-primary-400">
                      You're qualified — complete your interview.
                    </p>
                  </div>
                  <a href={`/interview/${a.interview_token}`}>
                    <Button size="sm" className="shrink-0">
                      Start interview
                    </Button>
                  </a>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {pendingSourcing.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-primary-700">Job invitations</h2>
          <ul className="space-y-3">
            {pendingSourcing.map((inv) => (
              <li key={inv.id}>
                <Card className="flex items-start justify-between gap-4 p-5">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-primary-900">{inv.job_title ?? "Role"}</h3>
                    {inv.company_name && (
                      <p className="mt-0.5 text-sm text-primary-500">{inv.company_name}</p>
                    )}
                    {inv.message && <p className="mt-2 text-sm text-primary-600">{inv.message}</p>}
                  </div>
                  <Button
                    size="sm"
                    loading={accepting === inv.id}
                    onClick={() => accept(inv.id)}
                    className="shrink-0"
                  >
                    Accept &amp; apply
                  </Button>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function MyApplications({ token }: { token: string }) {
  const [apps, setApps] = useState<CandidateApplication[] | null>(null);
  const [selected, setSelected] = useState<CandidateApplication | null>(null);

  useEffect(() => {
    void api.candidate.myApplications(token).then(setApps);
  }, [token]);

  if (!apps) return <Spinner label="Loading applications…" />;
  if (apps.length === 0)
    return (
      <EmptyState
        icon={briefcase}
        title="No applications yet"
        description="Roles you apply to — directly or by accepting an invitation — appear here."
      />
    );

  return (
    <>
      <ul className="space-y-3">
        {apps.map((a) => (
          <li key={a.id}>
            <Card interactive className="p-5" onClick={() => setSelected(a)}>
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <h3 className="font-semibold text-primary-900">{a.job_title ?? "Role"}</h3>
                  {a.company_name && (
                    <p className="mt-0.5 text-sm text-primary-500">{a.company_name}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {interviewActive(a) && <Badge status="invited">Interview ready</Badge>}
                  {a.feedback_token && <Badge status="evaluated">Feedback ready</Badge>}
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(
                      a.screening_status
                    )}`}
                  >
                    {a.screening_status === "pending" ? "Under review" : a.screening_status}
                  </span>
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ul>

      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.job_title ?? "Application"}>
        {selected && (
          <div className="space-y-4">
            {selected.company_name && (
              <p className="text-sm font-medium text-primary-500">{selected.company_name}</p>
            )}
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-primary-500">Screening:</span>
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(
                  selected.screening_status
                )}`}
              >
                {selected.screening_status === "pending" ? "Under review" : selected.screening_status}
              </span>
            </div>

            {interviewActive(selected) && (
              <div className="rounded-lg border border-brand-100 bg-brand-50/60 p-4">
                <p className="text-sm font-medium text-primary-800">You're invited to interview</p>
                <p className="mt-1 text-xs text-primary-500">
                  Complete your interview to move forward.
                </p>
                <a href={`/interview/${selected.interview_token}`}>
                  <Button size="sm" className="mt-3">
                    Start interview
                  </Button>
                </a>
              </div>
            )}

            {selected.feedback_token ? (
              <div className="rounded-lg border border-primary-100 bg-primary-50/60 p-4">
                <p className="text-sm font-medium text-primary-800">Interview feedback</p>
                {typeof selected.overall_score === "number" && (
                  <p className="mt-1 text-xs text-primary-500">
                    Overall score: {selected.overall_score}/100
                  </p>
                )}
                <a href={`/feedback/${selected.feedback_token}`} target="_blank" rel="noopener noreferrer">
                  <Button size="sm" variant="secondary" className="mt-3">
                    View feedback report
                  </Button>
                </a>
              </div>
            ) : (
              <p className="text-sm text-primary-500">
                Feedback will appear here once your interview has been evaluated.
              </p>
            )}
          </div>
        )}
      </Modal>
    </>
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
  const openToWork = !!profile?.open_to_work;

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

  async function toggleOpenToWork() {
    const next = !openToWork;
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

      <Card className="p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-primary-900">Open to work</h3>
            <p className="mt-1 max-w-md text-sm text-primary-500">
              When on, companies sourcing for roles can discover your profile. Your contact details
              stay private until you accept an invitation.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={openToWork}
            aria-label="Toggle open to work"
            disabled={savingToggle}
            onClick={toggleOpenToWork}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50 disabled:opacity-60 ${
              openToWork ? "bg-brand-600" : "bg-primary-300"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                openToWork ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>
      </Card>
    </div>
  );
}
