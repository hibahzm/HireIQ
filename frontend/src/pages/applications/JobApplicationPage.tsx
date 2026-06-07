import { useState } from "react";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const ACCEPTED_CV_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/jpeg",
  "image/png",
];
const ACCEPTED_CV_ACCEPT = ".pdf,.docx,.jpg,.jpeg,.png";

interface Props {
  jobId: string;
}

export default function JobApplicationPage({ jobId }: Props) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    if (!ACCEPTED_CV_TYPES.includes(file.type)) {
      setError("Accepted formats: PDF, DOCX, JPG, PNG.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("File must be under 10 MB.");
      return;
    }

    setSubmitting(true);
    setError(null);

    const form = new FormData();
    form.append("full_name", fullName);
    form.append("email", email);
    form.append("cv_file", file);

    try {
      const res = await fetch(`${BASE_URL}/jobs/${jobId}/applications`, {
        method: "POST",
        body: form,
      });
      if (res.status === 409) {
        setError("You've already applied to this position.");
      } else if (res.status === 422) {
        const data = await res.json();
        setError(data.detail ?? "Invalid submission.");
      } else if (res.status === 429) {
        setError("Too many submissions. Please try again later.");
      } else if (!res.ok) {
        setError("Submission failed. Please try again.");
      } else {
        setSuccess(true);
      }
    } catch {
      setError("Network error. Please check your connection.");
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full p-8 bg-white rounded-lg shadow text-center">
          <div className="text-green-600 text-4xl mb-4">✓</div>
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Application received!</h1>
          <p className="text-gray-600">
            Thank you for applying. We'll review your application and be in touch soon.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full p-8 bg-white rounded-lg shadow">
        <h1 className="text-xl font-semibold text-gray-900 mb-6">Apply for this position</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700">
              Full name
            </label>
            <input
              id="name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="cv" className="block text-sm font-medium text-gray-700">
              CV / Resume (PDF, DOCX, JPG, or PNG — max 10 MB)
            </label>
            <input
              id="cv"
              type="file"
              accept={ACCEPTED_CV_ACCEPT}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
              className="mt-1 block w-full text-sm text-gray-600 file:mr-4 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>
          {error && <p className="text-red-600 text-sm" role="alert">{error}</p>}
          <button
            type="submit"
            disabled={submitting || !file}
            className="w-full py-2 px-4 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit application"}
          </button>
        </form>
      </div>
    </div>
  );
}
