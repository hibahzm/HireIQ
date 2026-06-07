import { useEffect, useState } from "react";
import { api, ApiError, UserProfile } from "../../services/api";

interface Props {
  token: string;
  onBack: () => void;
}

export default function UserManagementPage({ token, onBack }: Props) {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"recruiter" | "admin">("recruiter");
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    api.users
      .list(token)
      .then(setUsers)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setError(null);
    try {
      const user = await api.users.create(token, { email: inviteEmail, role: inviteRole });
      setUsers((prev) => [...prev, user as UserProfile]);
      setInviteEmail("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invite failed");
    } finally {
      setInviting(false);
    }
  }

  async function handleRoleChange(userId: string, role: string) {
    try {
      const updated = await api.users.setRole(token, userId, role);
      setUsers((prev) => prev.map((u) => (u.id === userId ? (updated as UserProfile) : u)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Role update failed");
    }
  }

  async function handleDeactivate(userId: string) {
    if (!confirm("Deactivate this user?")) return;
    try {
      await api.users.deactivate(token, userId);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, is_active: false } : u))
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deactivation failed");
    }
  }

  if (loading) return <div className="p-8 text-gray-500">Loading users…</div>;

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-6">
        <button onClick={onBack} className="text-gray-500 hover:text-gray-700 text-sm">
          ← Back
        </button>
        <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
      </div>

      <form onSubmit={handleInvite} className="flex gap-2 mb-6">
        <input
          type="email"
          value={inviteEmail}
          onChange={(e) => setInviteEmail(e.target.value)}
          placeholder="user@company.com"
          required
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={inviteRole}
          onChange={(e) => setInviteRole(e.target.value as "recruiter" | "admin")}
          className="rounded-md border border-gray-300 px-2 py-2 text-sm"
        >
          <option value="recruiter">Recruiter</option>
          <option value="admin">Admin</option>
        </select>
        <button
          type="submit"
          disabled={inviting}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          {inviting ? "Inviting…" : "Invite"}
        </button>
      </form>

      {error && <p className="text-red-600 mb-4 text-sm" role="alert">{error}</p>}

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left py-2 font-medium text-gray-700">Email</th>
            <th className="text-left py-2 font-medium text-gray-700">Role</th>
            <th className="text-left py-2 font-medium text-gray-700">Status</th>
            <th className="py-2"></th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id} className="border-b hover:bg-gray-50">
              <td className="py-2">{user.email}</td>
              <td className="py-2">
                <select
                  value={user.role}
                  onChange={(e) => handleRoleChange(user.id, e.target.value)}
                  disabled={!user.is_active}
                  className="rounded border border-gray-300 px-1 py-0.5 text-xs"
                >
                  <option value="recruiter">Recruiter</option>
                  <option value="admin">Admin</option>
                </select>
              </td>
              <td className="py-2">
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    user.is_active
                      ? "bg-green-100 text-green-800"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {user.is_active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="py-2 text-right">
                {user.is_active && (
                  <button
                    onClick={() => handleDeactivate(user.id)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    Deactivate
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
