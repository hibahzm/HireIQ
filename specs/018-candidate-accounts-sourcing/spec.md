# Feature Specification: Candidate Accounts & In-App Talent Sourcing

**Feature Branch**: `018-candidate-accounts-sourcing`

**Created**: 2026-06-17

**Status**: Draft

**Input**: User description: "Add candidate accounts and in-app talent sourcing to the
currently company-only platform. Candidates register their own account, store one CV,
browse open jobs and one-click apply. Companies can enable in-app sourcing on a job and
discover open-to-work candidates via experience-aware search, then invite them."

## User Scenarios & Testing *(mandatory)*

This feature introduces a **second kind of user** — the *job-seeker* (candidate) — alongside
the existing *company* (hiring) user. Delivery is **phased**: Phase 1 (P1) makes candidate
accounts viable on their own; Phase 2 (P2) adds company-side sourcing that builds on the
candidate profiles created in Phase 1.

### User Story 1 — Job-seeker creates an account and stores a CV (Priority: P1)

A person looking for work registers an account, choosing "I'm looking for a job" rather than
"I'm hiring". They upload a single CV that becomes the basis of their profile, and they can
update or replace it later.

**Why this priority**: Nothing else for candidates works without an account and a stored CV.
It is the foundation for browsing, applying, and being sourced.

**Independent Test**: Register as a candidate, log in, upload a CV, see it reflected on the
profile, replace it, and log out/in again — entirely without any company involvement.

**Acceptance Scenarios**:

1. **Given** the registration screen, **When** a person selects "looking for a job" and
   submits a valid email + password, **Then** a candidate account is created and they are
   signed in as a candidate.
2. **Given** a signed-in candidate with no CV, **When** they upload a supported CV file,
   **Then** the CV is stored against their account and shown as their current CV.
3. **Given** a candidate with an existing CV, **When** they upload a new one, **Then** the
   new CV replaces the old one as the account's single current CV.
4. **Given** an email already registered (as a company user or a candidate), **When** someone
   tries to register that email again, **Then** registration is rejected with a clear message.

---

### User Story 2 — Job-seeker browses open jobs and applies in one click (Priority: P1)

A signed-in candidate browses jobs that companies have opened, and applies to a job with a
single action using the CV already on their account — no re-uploading.

**Why this priority**: This is the core value exchange for candidates and the first end-to-end
loop the platform can demonstrate. It reuses the existing screening pipeline.

**Independent Test**: As a candidate with a stored CV, open the jobs list, apply to a job in
one click, and confirm the application appears for that job and is screened.

**Acceptance Scenarios**:

1. **Given** a signed-in candidate with a stored CV, **When** they open the jobs list,
   **Then** they see only jobs that are open for applications.
2. **Given** a job they have not applied to, **When** they click apply, **Then** an
   application is created for that job using their stored CV and they get a confirmation.
3. **Given** a job they already applied to (via their account **or** via the public external
   link with the same email), **When** they try to apply again, **Then** the system blocks the
   duplicate and tells them they have already applied.
4. **Given** a new application, **When** it is created, **Then** it is screened by the same
   screening process used for external applications, and the CV used for screening is the one
   captured at the moment of applying.

---

### User Story 3 — Company enables in-app sourcing on a job (Priority: P2)

When posting or editing a job, a company chooses whether to keep the external application link
only, enable in-app sourcing (proactively searching candidates), or both.

**Why this priority**: Sourcing is opt-in per job and gates Story 4; it must exist before
companies can search, but it delivers no value until search (Story 4) is built.

**Independent Test**: Create/edit a job, toggle "enable in-app sourcing" on and off, and
confirm the setting persists and controls whether the sourcing search is available for that job.

**Acceptance Scenarios**:

1. **Given** a job being created or edited, **When** the company enables in-app sourcing,
   **Then** the job is marked as sourcing-enabled and the external link remains available.
2. **Given** a sourcing-disabled job, **When** a company member opens it, **Then** no sourcing
   search is offered for that job.

---

### User Story 4 — Company searches and invites candidates with experience-aware ranking (Priority: P2)

For a sourcing-enabled job, a company searches the pool of candidates who are open to work and
gets a ranked shortlist whose ordering reflects how well each candidate's skills **and years of
experience** match the job. The company invites promising candidates; an invited candidate who
accepts becomes an applicant.

**Why this priority**: This is the headline sourcing capability. It depends on candidate
profiles (Story 1) and the sourcing toggle (Story 3).

**Independent Test**: With several open-to-work candidates whose CVs differ in years of a key
skill, run a search for a job requiring that skill and verify the candidate with more relevant
years ranks above one with fewer; invite one and confirm they receive an invitation and, on
acceptance, appear as a (deduplicated) applicant.

**Acceptance Scenarios**:

1. **Given** a sourcing-enabled job and a pool of candidates, **When** the company searches,
   **Then** only candidates marked open-to-work appear in the results.
2. **Given** two candidates equally matched on a required skill except one has 3 years and the
   other 2 years of it, **When** the search runs, **Then** the 3-year candidate ranks higher.
3. **Given** a search result, **When** the company views a candidate before inviting them,
   **Then** the candidate's direct contact details are not revealed.
4. **Given** a candidate in the results, **When** the company sends an invitation, **Then** the
   candidate receives an invitation link for that job.
5. **Given** an invitation, **When** the candidate accepts it, **Then** an application is
   created for that job (deduplicated against any existing application for the same job/email).

---

### User Story 5 — Job-seeker manages availability and invitations (Priority: P2)

A candidate controls whether they are discoverable ("open to work") and reviews/accepts
invitations companies have sent them.

**Why this priority**: Consent and invitation handling are required for the sourcing loop to be
ethical and complete, but they sit on top of the core sourcing search.

**Independent Test**: Toggle open-to-work off and confirm the candidate stops appearing in
company searches; receive an invitation, accept it, and confirm an application is created.

**Acceptance Scenarios**:

1. **Given** a candidate, **When** they turn off open-to-work, **Then** they no longer appear
   in any company's sourcing search.
2. **Given** a candidate with a pending invitation, **When** they view their invitations,
   **Then** they see the inviting company and role and can accept.

---

### Edge Cases

- **Duplicate identity across routes**: a person has a candidate account *and* applies to the
  same job via the public external link with the same email — only one application may exist per
  job per email; the second attempt is blocked.
- **Very long CV**: a CV exceeds the size the matching index can represent — the system keeps
  the most-recent experience and records that the CV was shortened for indexing, rather than
  silently dropping content.
- **CV with vague experience phrasing** ("extensive experience", "several years") — the system
  must not invent a specific number of years; such skills are treated as present-but-unquantified.
- **Candidate with no CV** tries to apply or expects to be sourced — applying is blocked with a
  prompt to upload a CV; they do not appear in sourcing results.
- **Account-type mismatch**: a candidate credential used on a company-only screen (or vice
  versa) is rejected; a candidate cannot access company hiring data and vice versa.
- **Job closed between browse and apply** — applying to a no-longer-open job fails gracefully.
- **Candidate edits CV after applying** — past applications and their screening results are
  unchanged; only future applications and sourcing use the new CV.
- **Invitation to a candidate who later turns off open-to-work or already applied** — accepting
  still resolves to a single deduplicated application.

## Requirements *(mandatory)*

### Functional Requirements

**Accounts & identity**

- **FR-001**: The system MUST let a person register as either a *company* (hiring) or a
  *candidate* (job-seeking), chosen at registration.
- **FR-002**: The system MUST enforce a single global uniqueness of email across all accounts,
  so one email maps to at most one account regardless of type.
- **FR-003**: The system MUST authenticate candidates with their own session that grants access
  only to candidate capabilities, and MUST reject candidate credentials on company-only
  capabilities and vice versa.
- **FR-004**: Candidates MUST be able to view and update their own profile, including an
  *open-to-work* availability setting that defaults to off.

**Candidate CV**

- **FR-005**: Each candidate MUST be able to store exactly one current CV, and replacing it
  MUST supersede the previous one.
- **FR-006**: The system MUST extract text from an uploaded CV and build a searchable profile
  from the whole CV (not fragments).
- **FR-007**: When a CV is too large to fully index, the system MUST prioritize the most-recent
  experience and MUST record (auditably) that the CV was shortened for indexing; it MUST NOT
  silently discard content.
- **FR-008**: The system MUST derive a structured record of the candidate's skills and the
  associated years of experience, distinguishing stated years, years inferred from dates, and
  unquantified ("present but unknown") skills, and MUST NOT fabricate a number of years.

**Browse & apply**

- **FR-009**: Candidates MUST be able to browse jobs that are open for applications.
- **FR-010**: Candidates MUST be able to apply to a job in one action using their stored CV.
- **FR-011**: The system MUST capture the candidate's CV onto the application at the moment of
  applying so that the screening result reflects the CV as it was then, independent of later
  CV edits.
- **FR-012**: The system MUST prevent more than one application per job per email, whether the
  applications arrive via a candidate account or the public external link.
- **FR-013**: Account-based applications MUST be screened by the same screening process as
  external applications.

**Company sourcing**

- **FR-014**: A company MUST be able to enable or disable in-app sourcing per job, independently
  of (and in addition to) the external application link.
- **FR-015**: For a sourcing-enabled job, a company MUST be able to search the candidate pool
  and receive a ranked shortlist for that job.
- **FR-016**: Sourcing results MUST include only candidates who are open to work.
- **FR-017**: Ranking MUST be experience-aware: for a required skill, a candidate with more
  relevant years MUST rank above an otherwise-equivalent candidate with fewer years.
- **FR-018**: Sourcing MUST NOT reveal a candidate's direct contact details before the candidate
  accepts an invitation.
- **FR-019**: A company MUST be able to send a job invitation to a sourced candidate, who then
  receives an invitation link.
- **FR-020**: When a candidate accepts an invitation, the system MUST create an application for
  that job, deduplicated against any existing application for the same job/email.

**Isolation & safety**

- **FR-021**: A candidate MUST NOT be able to read any company's hiring data (other applicants,
  evaluations, etc.), and a company MUST NOT be able to read candidate data beyond what sourcing
  exposes for open-to-work candidates.

### Key Entities *(include if feature involves data)*

- **Candidate account**: a job-seeker identity — email (globally unique), credentials,
  active/availability status (open-to-work). Distinct from a company hiring user; not owned by
  any company.
- **Candidate CV**: the single current CV per candidate — original file, extracted text, a
  whole-CV searchable representation, and a structured skills-and-years record. The source for
  browsing/applying and for sourcing search.
- **Job (extended)**: gains a per-job *sourcing-enabled* setting; retains its external
  application link and open/closed status.
- **Application (reused)**: the link between a candidate and a job, carrying the CV snapshot used
  for screening. One per job per email.
- **Invitation**: a company's offer to a sourced candidate for a specific job; on acceptance it
  becomes a (deduplicated) application.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new candidate can register, upload a CV, and submit a first application in under
  5 minutes without contacting support.
- **SC-002**: A returning candidate can apply to a browsed job in a single action (one click,
  no re-upload).
- **SC-003**: For a required skill, a candidate with more relevant years of that skill ranks
  above an otherwise-equivalent candidate with fewer years in 100% of head-to-head test cases.
- **SC-004**: No email can produce more than one application per job, across both the account and
  external routes (0 duplicates).
- **SC-005**: Candidates who are not open-to-work never appear in any sourcing result (0 leaks),
  and contact details are never shown for a candidate who has not accepted an invitation.
- **SC-006**: A candidate's edits to their CV do not change the screening outcome of any
  application submitted before the edit.

## Assumptions

- The existing global candidate records and the public external application flow remain; candidate
  accounts extend that same identity space (one email = one identity).
- The existing CV text-extraction and screening pipeline is reused unchanged for account-based
  applications; only the source of the CV (stored profile vs. uploaded file) differs.
- Email/password authentication is reused (same mechanism as company users); no new SSO/OAuth.
- "Years of experience" for ranking is derived from CV content; where the CV is vague, the skill
  is treated as present-but-unquantified rather than assigned a guessed number.
- Browsing shows only jobs that are open for applications (the existing public-readable job set).
- Phase 1 (Stories 1–2) is shippable and testable without Phase 2; Phase 2 (Stories 3–5) depends
  on candidate profiles created in Phase 1.
- Multi-tenant isolation is preserved: candidate data is intentionally cross-company for sourcing,
  but companies see only open-to-work candidates and only the fields sourcing exposes.
