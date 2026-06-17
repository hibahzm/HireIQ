import { useState } from "react";
import { api, ApiError } from "../../services/api";
import AuthLayout, { Field } from "../../components/AuthLayout";
import Button from "../../components/ui/Button";

interface Props {
  onBackToLogin: () => void;
}

export default function ForgotPasswordPage({ onBackToLogin }: Props) {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.auth.forgotPassword(email);
      // Always succeeds (the API never reveals whether the account exists).
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <AuthLayout
        title="Check your email"
        subtitle="If an account exists for that address, we've sent a password reset link. It expires in 1 hour."
      >
        <Button type="button" onClick={onBackToLogin} className="w-full">
          Back to sign in
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Forgot your password?"
      subtitle="Enter your email and we'll send you a link to reset it."
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
        {error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" loading={loading} className="w-full">
          Send reset link
        </Button>
        <button
          type="button"
          onClick={onBackToLogin}
          className="w-full text-sm text-primary-500 hover:text-primary-700"
        >
          Back to sign in
        </button>
      </form>
    </AuthLayout>
  );
}
