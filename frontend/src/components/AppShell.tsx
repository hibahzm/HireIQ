import { useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { crumbsFor } from "./breadcrumbs";
import {
  ArrowLeftIcon,
  BriefcaseIcon,
  ChevronRightIcon,
  CloseIcon,
  DashboardIcon,
  LogOutIcon,
  MenuIcon,
  RefreshIcon,
  UsersIcon,
} from "./ui/icons";
import { LogoMark } from "./ui/Logo";

const NAV = [
  { to: "/overview", label: "Overview", Icon: DashboardIcon },
  { to: "/jobs", label: "Jobs", Icon: BriefcaseIcon },
];

const ADMIN_NAV = [{ to: "/users", label: "Team", Icon: UsersIcon }];
const MANAGER_NAV = [{ to: "/platform", label: "Platform", Icon: DashboardIcon }];

function initials(email?: string): string {
  if (!email) return "··";
  return email.slice(0, 2).toUpperCase();
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  // Bumping this remounts <main>, which re-runs every page's data-fetch effects —
  // a universal "refresh this page" without each page needing its own reload logic.
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const crumbs = crumbsFor(location.pathname);
  const canGoBack = crumbs.length > 1;

  function handleRefresh() {
    setRefreshing(true);
    setRefreshKey((k) => k + 1);
    // Brief spin for feedback; the remount itself is synchronous.
    window.setTimeout(() => setRefreshing(false), 600);
  }
  const navItems =
    user?.role === "manager"
      ? MANAGER_NAV
      : user?.role === "admin"
      ? [...NAV, ...ADMIN_NAV]
      : NAV;

  const sidebar = (
    <div className="flex h-full flex-col bg-primary-800 text-primary-100">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/95 p-1 shadow-sm">
          <LogoMark size={26} />
        </span>
        <span className="text-lg font-extrabold tracking-tight">
          <span className="text-white">Hire</span>
          <span className="text-brand-400">IQ</span>
        </span>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-2">
        {navItems.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-150 ${
                isActive
                  ? "bg-primary-700 text-white"
                  : "text-primary-300 hover:bg-primary-700/60 hover:text-white"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className="absolute inset-y-2 left-0 w-1 rounded-r-full bg-brand-400 animate-scale-in" />
                )}
                <Icon className="transition-transform duration-150 group-hover:scale-110" />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-primary-700 p-3">
        <button
          onClick={() => void logout()}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-primary-300 transition-colors duration-150 hover:bg-primary-700/60 hover:text-white cursor-pointer"
        >
          <LogOutIcon />
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-canvas">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">{sidebar}</aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-primary-900/50 animate-fade-in"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-64 animate-slide-in-left shadow-2xl">{sidebar}</div>
        </div>
      )}

      <div className="lg:pl-64">
        {/* Top bar */}
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-primary-100 bg-surface/90 px-4 backdrop-blur sm:px-6">
          <button
            className="rounded-lg p-2 text-primary-500 hover:bg-primary-100 lg:hidden cursor-pointer"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation menu"
          >
            <MenuIcon />
          </button>

          {canGoBack && (
            <button
              onClick={() => navigate(-1)}
              className="rounded-lg p-2 text-primary-500 hover:bg-primary-100 cursor-pointer"
              aria-label="Go back"
            >
              <ArrowLeftIcon />
            </button>
          )}

          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
            {crumbs.map((c, i) => {
              const last = i === crumbs.length - 1;
              return (
                <span key={i} className="flex items-center gap-1.5">
                  {i > 0 && <ChevronRightIcon className="h-4 w-4 text-primary-300" />}
                  {c.to && !last ? (
                    <Link to={c.to} className="text-primary-500 hover:text-primary-800">
                      {c.label}
                    </Link>
                  ) : (
                    <span className={last ? "font-semibold text-primary-800" : "text-primary-500"}>
                      {c.label}
                    </span>
                  )}
                </span>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <button
              onClick={handleRefresh}
              className="rounded-lg p-2 text-primary-500 transition-colors hover:bg-primary-100 hover:text-primary-800 cursor-pointer"
              aria-label="Refresh this page"
              title="Refresh"
            >
              <RefreshIcon className={refreshing ? "animate-spin" : undefined} />
            </button>
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium leading-tight text-primary-800">
                {user?.email ?? "—"}
              </p>
              {user?.role && (
                <p className="text-xs capitalize leading-tight text-primary-400">{user.role}</p>
              )}
            </div>
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-700 text-sm font-bold text-white shadow-sm ring-2 ring-brand-100">
              {initials(user?.email)}
            </span>
          </div>
        </header>

        {/* Mobile close affordance when drawer open */}
        {mobileOpen && (
          <button
            className="fixed right-4 top-4 z-50 rounded-lg bg-surface p-2 text-primary-600 shadow-card lg:hidden cursor-pointer"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation menu"
          >
            <CloseIcon />
          </button>
        )}

        {/* Keyed by pathname (+ refresh nonce) so content re-animates on every
            navigation and remounts — re-fetching data — when Refresh is clicked. */}
        <main
          key={`${location.pathname}#${refreshKey}`}
          className="mx-auto max-w-7xl animate-fade-in-up px-4 py-6 sm:px-6 lg:px-8"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
