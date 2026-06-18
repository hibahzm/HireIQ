import { useRef, useState } from "react";
import { api, ApiError, type CandidateProfile } from "../../services/api";
import Card from "../../components/ui/Card";
import Button from "../../components/ui/Button";
import Badge from "../../components/ui/Badge";
import { type Notify } from "./shared";

export default function ProfileTab({
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
