import { useState } from "react";
import { api, ApiError } from "../../services/api";
import AuthLayout, { Field } from "../../components/AuthLayout";
import Button from "../../components/ui/Button";

interface Props {
  onSuccess: (token: string) => void;
  onRegister: () => void;
  onForgotPassword: () => void;
}

export default function LoginPage({ onSuccess, onRegister, onForgotPassword }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.auth.login({ email, password });
      onSuccess(res.access_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      title="Sign in to HireIQ"
      subtitle="Welcome back — sign in to manage your hiring."
      footer={
        <>
          No account?{" "}
          <button onClick={onRegister} className="font-medium text-brand-700 hover:underline cursor-pointer">
            Register your company
          </button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field
          id="email"
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
        />
        <Field
          id="password"
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
        />
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <Button type="submit" loading={loading} className="w-full">
          Sign in
        </Button>
        <button
          type="button"
          onClick={onForgotPassword}
          className="w-full text-sm text-primary-500 hover:text-primary-700"
        >
          Forgot your password?
        </button>
      </form>
    </AuthLayout>
  );
}
