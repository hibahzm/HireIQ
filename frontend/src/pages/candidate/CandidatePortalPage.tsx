import { useCallback, useEffect, useState } from "react";
import { api, type CandidateProfile } from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import Logo from "../../components/ui/Logo";
import Button from "../../components/ui/Button";
import { LogOutIcon } from "../../components/ui/icons";
import BrowseJobsTab from "./BrowseJobsTab";
import InvitationsTab from "./InvitationsTab";
import MyApplicationsTab from "./MyApplicationsTab";
import ProfileTab from "./ProfileTab";

type Tab = "jobs" | "invitations" | "applications" | "profile";

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
          {tab === "jobs" && (
            <BrowseJobsTab token={t} hasCv={!!profile?.has_cv} onNotify={setBanner} />
          )}
          {tab === "invitations" && <InvitationsTab token={t} onNotify={setBanner} />}
          {tab === "applications" && <MyApplicationsTab token={t} />}
          {tab === "profile" && (
            <ProfileTab token={t} profile={profile} onChanged={loadProfile} onNotify={setBanner} />
          )}
        </div>
      </main>
    </div>
  );
}
