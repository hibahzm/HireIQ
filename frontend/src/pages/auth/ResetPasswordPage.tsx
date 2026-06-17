import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../services/api";
import AuthLayout, { Field } from "../../components/AuthLayout";
import Button from "../../components/ui/Button";

interface Props {
  onSuccess: (token: string) => void;
}

export default function ResetPasswordPage({ onSuccess }: Props) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) setError("Invalid or missing reset link. Request a new one from the sign-in page.");
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await api.auth.resetPassword({ token, new_password: password });
      onSuccess(res.access_token);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? "This reset link is invalid or has expired. Request a new one."
          : "Failed to reset password."
      );
      setLoading(false);
    }
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="Set a new password for your HireIQ account.">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field
          id="password"
          label="New password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          disabled={!token}
          autoComplete="new-password"
        />
        <Field
          id="confirm"
          label="Confirm password"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
          minLength={8}
          disabled={!token}
          autoComplete="new-password"
        />
        {error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} disabled={!token} className="w-full">
          Reset password &amp; sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
