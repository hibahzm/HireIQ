import { useState } from "react";
import { api, ApiError } from "../../services/api";
import AuthLayout, { Field } from "../../components/AuthLayout";
import Button from "../../components/ui/Button";
import AccountTypeToggle, { type AccountType } from "../../components/ui/AccountTypeToggle";

interface Props {
  onSuccess: (token: string) => void;
  onLogin: () => void;
}

export default function RegisterPage({ onSuccess, onLogin }: Props) {
  const [accountType, setAccountType] = useState<AccountType>("company");
  const [companyName, setCompanyName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const isCandidate = accountType === "candidate";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = isCandidate
        ? await api.candidateAuth.register({ email, full_name: fullName, password })
        : await api.auth.register({ company_name: companyName, email, password });
      onSuccess(res.access_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      title="Create your HireIQ account"
      subtitle={
        isCandidate
          ? "Build your profile and apply to roles in one click."
          : "Set up your company workspace in a minute."
      }
      footer={
        <>
          Already have an account?{" "}
          <button onClick={onLogin} className="font-medium text-brand-700 hover:underline cursor-pointer">
            Sign in
          </button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <AccountTypeToggle value={accountType} onChange={setAccountType} />
        {isCandidate ? (
          <Field
            id="full_name"
            label="Full name"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        ) : (
          <Field
            id="company"
            label="Company name"
            type="text"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            required
          />
        )}
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
          minLength={8}
          autoComplete="new-password"
        />
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <Button type="submit" loading={loading} className="w-full">
          Create account
        </Button>
      </form>
    </AuthLayout>
  );
}
