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

type Tab = "jobs" | "invitations" | "applications" | "profile";

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

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <Logo size={32} />
        <div className="flex items-center gap-3">
          {profile && <span className="text-sm text-slate-500">{profile.email}</span>}
          <Button size="sm" variant="secondary" onClick={() => void logout()}>
            Sign out
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-2xl font-bold text-slate-900">
          Welcome{profile?.full_name ? `, ${profile.full_name}` : ""}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Manage your CV, browse open roles, and apply in one click.
        </p>

        {banner && (
          <div
            role="status"
            className={[
              "mt-4 rounded-lg px-4 py-2 text-sm",
              banner.kind === "ok"
                ? "bg-emerald-50 text-emerald-700"
                : "bg-red-50 text-red-700",
            ].join(" ")}
          >
            {banner.text}
          </div>
        )}

        <nav className="mt-6 flex gap-1 rounded-xl bg-slate-100 p-1">
          {(
            [
              ["jobs", "Browse jobs"],
              ["invitations", "Invitations"],
              ["applications", "My applications"],
              ["profile", "My CV & profile"],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={[
                "flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-colors cursor-pointer",
                tab === key ? "bg-white text-brand-700 shadow-sm" : "text-slate-500 hover:text-slate-700",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="mt-6">
          {tab === "jobs" && (
            <BrowseJobs token={t} hasCv={!!profile?.has_cv} onNotify={setBanner} />
          )}
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

type Notify = (b: { kind: "ok" | "err"; text: string }) => void;

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
      onNotify({ kind: "ok", text: "Application submitted!" });
      await load();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Could not apply" });
    } finally {
      setApplying(null);
    }
  }

  if (!jobs) return <Spinner />;
  if (jobs.length === 0)
    return <p className="text-sm text-slate-500">No open roles right now. Check back soon.</p>;

  return (
    <div className="space-y-3">
      {!hasCv && (
        <p className="rounded-lg bg-amber-50 px-4 py-2 text-sm text-amber-700">
          Upload a CV in “My CV & profile” before you can apply.
        </p>
      )}
      {jobs.map((job) => (
        <Card key={job.id} className="flex items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-slate-900">{job.title}</h3>
            {job.company_name && <p className="text-sm text-slate-500">{job.company_name}</p>}
            {job.description && (
              <p className="mt-1 line-clamp-2 text-sm text-slate-600">{job.description}</p>
            )}
          </div>
          <Button
            size="sm"
            disabled={!hasCv || job.already_applied}
            loading={applying === job.id}
            onClick={() => apply(job.id)}
          >
            {job.already_applied ? "Applied" : "Apply"}
          </Button>
        </Card>
      ))}
    </div>
  );
}

function MyApplications({ token }: { token: string }) {
  const [apps, setApps] = useState<CandidateApplication[] | null>(null);

  useEffect(() => {
    void api.candidate.myApplications(token).then(setApps);
  }, [token]);

  if (!apps) return <Spinner />;
  if (apps.length === 0)
    return <p className="text-sm text-slate-500">You haven’t applied to any roles yet.</p>;

  return (
    <div className="space-y-3">
      {apps.map((a) => (
        <Card key={a.id} className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-900">{a.job_title ?? "Role"}</h3>
            {a.company_name && <p className="text-sm text-slate-500">{a.company_name}</p>}
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium capitalize text-slate-600">
            {a.screening_status === "pending" ? "Under review" : a.screening_status}
          </span>
        </Card>
      ))}
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

  if (!invites) return <Spinner />;
  if (invites.length === 0)
    return <p className="text-sm text-slate-500">No invitations yet.</p>;

  return (
    <div className="space-y-3">
      {invites.map((inv) => (
        <Card key={inv.id} className="flex items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-slate-900">{inv.job_title ?? "Role"}</h3>
            {inv.company_name && <p className="text-sm text-slate-500">{inv.company_name}</p>}
            {inv.message && <p className="mt-1 text-sm text-slate-600">{inv.message}</p>}
          </div>
          {inv.status === "pending" ? (
            <Button size="sm" loading={accepting === inv.id} onClick={() => accept(inv.id)}>
              Accept &amp; apply
            </Button>
          ) : (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium capitalize text-slate-600">
              {inv.status}
            </span>
          )}
        </Card>
      ))}
    </div>
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
    try {
      await api.candidateAuth.updateProfile(token, { open_to_work: next });
      onNotify({
        kind: "ok",
        text: next ? "You're now discoverable by companies." : "You're hidden from company search.",
      });
      await onChanged();
    } catch (err) {
      onNotify({ kind: "err", text: err instanceof ApiError ? err.message : "Update failed" });
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <h3 className="font-semibold text-slate-900">Your CV</h3>
        <p className="mt-1 text-sm text-slate-500">
          {profile?.has_cv ? "A CV is on file. Uploading a new one replaces it." : "No CV uploaded yet."}
        </p>
        {truncated && (
          <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
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
        <Button
          className="mt-3"
          size="sm"
          loading={uploading}
          onClick={() => fileRef.current?.click()}
        >
          {profile?.has_cv ? "Replace CV" : "Upload CV"}
        </Button>
      </Card>

      <Card className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-slate-900">Open to work</h3>
          <p className="mt-1 text-sm text-slate-500">
            When on, companies sourcing for roles can discover you.
          </p>
        </div>
        <button
          role="switch"
          aria-checked={!!profile?.open_to_work}
          onClick={() => toggleOpenToWork(!profile?.open_to_work)}
          className={[
            "relative h-6 w-11 rounded-full transition-colors cursor-pointer",
            profile?.open_to_work ? "bg-brand-600" : "bg-slate-300",
          ].join(" ")}
        >
          <span
            className={[
              "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform",
              profile?.open_to_work ? "translate-x-[22px]" : "translate-x-0.5",
            ].join(" ")}
          />
        </button>
      </Card>
    </div>
  );
}
