# Feature Specification: HireIQ — AI-Powered Hiring Platform (MVP)

**Feature Branch**: `001-ai-hiring-platform`

**Created**: 2026-06-04

**Status**: Draft

**Input**: Full engineering plan — HireIQ MVP covering job setup, CV screening, voice interview, evaluation, and Azure deployment

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Recruiter Sets Up a Job with AI-Guided Criteria (Priority: P1)

A recruiter creates a new job posting and has a guided conversation with an AI assistant that helps
define the evaluation framework: required skills, nice-to-have skills, experience level, evaluation
dimensions with relative weights, and disqualifying conditions (dealbreakers). The AI confirms the
criteria and activates the job for applications.

**Why this priority**: Without a completed job with defined criteria, no other part of the pipeline
can function. Screening, interviewing, and evaluating all depend on the criteria produced here.

**Independent Test**: Create a company account, start a job setup conversation, answer the AI's
questions, and confirm the criteria. The job should appear as "active" and be ready to accept
applications. No other feature is needed.

**Acceptance Scenarios**:

1. **Given** a recruiter is logged in, **When** they create a job and begin the setup conversation,
   **Then** the AI asks targeted questions to extract required skills, experience level, and
   evaluation dimensions.
2. **Given** the setup conversation is in progress, **When** the recruiter provides all required
   information, **Then** the AI confirms the criteria and marks the job as active.
3. **Given** a job is active, **When** a recruiter views their dashboard, **Then** the job appears
   with its status and is open to applications.
4. **Given** a recruiter has not completed the setup conversation, **When** they attempt to activate
   the job, **Then** the system prevents activation and explains what information is still needed.

---

### User Story 2 — Candidate Applies and Gets Screened (Priority: P2)

A candidate visits the job application page, submits their name, email, and CV (as a PDF). The
system extracts the CV content automatically — including scanned documents — and screens it against
the job's evaluation criteria. The candidate receives a confirmation email. The recruiter sees each
applicant's screening result (score, rationale, qualified/rejected status) on the job detail page.

**Why this priority**: CV screening is the first automated step and the gating action for interview
invitations. It delivers immediate value to recruiters and is independently verifiable.

**Independent Test**: Submit a PDF CV to an active job. Within 2 minutes, the recruiter should see
a screening result with a score and rationale. The candidate should receive a confirmation email.

**Acceptance Scenarios**:

1. **Given** an active job exists, **When** a candidate submits their name, email, and PDF CV,
   **Then** the system accepts the application and sends a confirmation email to the candidate.
2. **Given** an application is submitted, **When** the screening completes, **Then** the recruiter
   sees a score (0–100), a rationale explaining the score, and a status of "qualified" or
   "rejected" for the candidate.
3. **Given** the CV is a scanned image with no extractable text, **When** the system processes it,
   **Then** the system still extracts the CV content and produces a screening result.
4. **Given** a candidate has already applied to a job, **When** they attempt to apply again,
   **Then** the system rejects the duplicate and informs the candidate.
5. **Given** a candidate is rejected, **When** the recruiter views the application, **Then** the
   rejection rationale clearly references which required criteria were not met.

---

### User Story 3 — Candidate Completes a Voice Interview (Priority: P3)

A qualified candidate receives an interview invitation email containing a secure, one-time link.
They click the link and enter an interview room where an AI conducts a structured voice interview —
asking questions, listening to responses, and adapting its questions based on what the candidate
says. The interview ends when all evaluation dimensions have been explored or the maximum number
of turns is reached. The candidate sees a "thank you" screen when the interview is complete.

**Why this priority**: The voice interview is HireIQ's primary differentiator. Screening alone is
a commodity — the interview is what makes evaluations meaningful.

**Independent Test**: Send an interview invitation to a qualified candidate. The candidate clicks
the link, speaks answers to interview questions, hears the AI's voice responses, and reaches the
completion screen. Full transcript is stored and viewable by the recruiter.

**Acceptance Scenarios**:

1. **Given** a candidate is marked "qualified," **When** the recruiter triggers interview invitations,
   **Then** the candidate receives an email with a unique, time-limited interview link.
2. **Given** a candidate opens the interview link, **When** they enter the interview room,
   **Then** they can hear the AI's opening question within 5 seconds.
3. **Given** a candidate speaks their answer, **When** the AI processes it, **Then** the AI
   responds with a relevant follow-up question delivered in voice within 10 seconds.
4. **Given** all evaluation dimensions are covered, **When** the AI concludes the interview,
   **Then** the candidate sees a completion message and the session is marked complete.
5. **Given** a candidate uses an expired or already-used interview link, **When** they attempt to
   connect, **Then** they see a clear expiry message and cannot proceed.
6. **Given** a candidate submits a response that is harmful or entirely unrelated to the interview,
   **When** the system detects this, **Then** the response is blocked and the AI redirects
   the conversation without storing the problematic content.

---

### User Story 4 — Recruiter Reviews Evaluations and Shortlists (Priority: P4)

After interviews complete, the recruiter views a ranked shortlist of all evaluated candidates for
a job. Each candidate card shows their overall score, a hire/no-hire recommendation, and
high-level strengths. The recruiter can open a candidate's profile to see: per-dimension scores
with supporting quotes from the interview, consistency flags between CV claims and interview
answers, communication quality metrics, and the full transcript with the ability to play back
audio recordings.

**Why this priority**: This is the recruiter's primary decision-making surface. Without it,
the interview data has no actionable output.

**Independent Test**: Complete at least one interview for a job. Open the job's dashboard. The
candidate should appear in a ranked list with a score and recommendation. Click through to see
the full evaluation breakdown.

**Acceptance Scenarios**:

1. **Given** at least one interview is complete for a job, **When** the recruiter views the job,
   **Then** they see a ranked list of candidates ordered by overall score.
2. **Given** a recruiter opens a candidate's evaluation, **When** they view the dimension scores,
   **Then** each dimension shows a score and at least one supporting quote from the interview.
3. **Given** an evaluation includes consistency flags, **When** the recruiter views the profile,
   **Then** any CV claims not supported or contradicted by interview responses are highlighted.
4. **Given** an evaluation has low confidence, **When** the recruiter views the profile,
   **Then** a visible warning indicates the evaluation quality is uncertain and may need
   human review.
5. **Given** an interview was conducted via voice, **When** the recruiter reviews the transcript,
   **Then** they can play back the audio recording for any turn.

---

### User Story 5 — Candidate Receives a Feedback Report (Priority: P5)

After evaluation results are ready, the candidate receives a feedback email. They can access a
feedback report via a secure token link (no account required) that shows their performance across
evaluation dimensions and general feedback on strengths and areas for improvement.

**Why this priority**: Candidate experience is a secondary but important concern. Feedback builds
trust in the hiring process and encourages future engagement with companies using HireIQ.

**Independent Test**: Complete an interview and evaluation. The candidate receives a feedback email.
They click the link and see a feedback report with dimension scores and a written summary.

**Acceptance Scenarios**:

1. **Given** an evaluation is complete, **When** the system processes it, **Then** the candidate
   receives a feedback email within 30 minutes of interview completion.
2. **Given** a candidate opens the feedback link, **When** they view the report, **Then** they see
   scores for each evaluation dimension and a written summary of strengths and areas for growth.
3. **Given** a candidate opens the feedback link, **When** they view the report, **Then** no
   personally identifying information from other candidates is visible.
4. **Given** an expired or invalid feedback token, **When** a candidate attempts to access the
   report, **Then** they see a clear message that the link is no longer valid.

---

### Edge Cases

- A corrupted or password-protected PDF is rejected immediately; the candidate sees a clear
  error and is prompted to re-upload. No application record is created.
- If the candidate goes silent during a voice interview (STT returns an empty transcript), the AI
  prompts them to speak louder or switch to text input. The silence does not consume a turn.
  After 3 consecutive silent turns the session is preserved as resumable (system_interrupted)
  and the candidate is notified via the interview UI.
- An interrupted interview session can be resumed by the candidate within 24 hours from the
  last completed turn. After 24 hours the session expires; completed turns are retained.
- If the same candidate email is used to apply to two different jobs at the same company, each
  application is treated as independent — separate screening, separate interview, separate
  evaluation. The candidate record is shared but the application pipeline is fully isolated per
  job (see Assumptions).
- What happens if the AI evaluation produces a very low quality score across all dimensions
  (candidate gave one-word answers)?
- A recruiter cannot delete a job that has applications in an active state (screening, qualified,
  invited, or interviewing). The system returns a 409 error explaining that the job must be
  closed first and all active applications resolved. Once no active applications remain, deletion
  is permitted and cascades to all related records.
- If the AI service is unavailable mid-interview, the candidate sees a clear error; the session
  is preserved as resumable within the 24-hour window; the recruiter sees it as system-interrupted,
  not abandoned.

## Requirements *(mandatory)*

### Functional Requirements

**Authentication & Multi-Company Access**

- **FR-001**: System MUST allow a company to register with a company name, admin email, and
  password.
- **FR-002**: System MUST authenticate company users with email and password; sessions MUST expire
  and require re-authentication.
- **FR-003**: System MUST enforce role-based access: admins can manage company users and settings;
  recruiters can manage jobs, applications, and evaluations only.
- **FR-004**: Each company's data MUST be completely isolated — a user from Company A MUST NOT be
  able to view or access any data belonging to Company B under any circumstances.

**Job Setup**

- **FR-005**: Recruiters MUST be able to create a job posting with at minimum a job title.
- **FR-006**: System MUST offer an AI-guided setup conversation that elicits required skills,
  optional skills, experience level, evaluation dimensions with weights, dealbreakers, and a
  minimum CV screening score threshold (0–100) that determines qualification.
- **FR-007**: A job MUST only become active after the setup conversation produces a complete,
  confirmed set of evaluation criteria.
- **FR-008**: Recruiters MUST be able to view all their company's jobs and their current status
  (draft, setup, active, paused, closed) on a dashboard. The `setup` status indicates the
  AI-guided criteria conversation is in progress.

**CV Application & Screening**

- **FR-009**: Candidates MUST be able to submit their full name, email address, and CV (PDF) to
  apply for an active job — no account required.
- **FR-010**: System MUST automatically extract text content from submitted CVs; the extraction
  MUST handle both text-based PDFs and scanned/image-based PDFs. If a file is corrupted,
  password-protected, or otherwise unreadable after extraction attempts, the system MUST reject
  the upload immediately with a clear error message and prompt the candidate to re-upload a
  readable file; the application MUST NOT be created for an unreadable CV.
- **FR-011**: System MUST automatically screen each CV against the job's criteria and produce:
  a score between 0 and 100, a written rationale, and a status of "qualified" (score ≥ the
  recruiter-set threshold) or "rejected" (score below threshold).
- **FR-012**: Candidates MUST receive an automated confirmation email immediately after applying.
- **FR-013**: System MUST reject duplicate applications where the same candidate email is used
  for the same job.
- **FR-014**: Recruiters MUST be able to view all applications for a job with screening results.

**Voice Interview**

- **FR-015**: Qualified candidates MUST receive an interview invitation email containing a
  unique access link that expires 7 days after sending — no account creation required.
- **FR-016**: Candidates MUST be able to join the interview room using only their invitation link.
- **FR-017**: The interview MUST support voice input from the candidate (speaking into a microphone)
  and voice output from the AI (spoken responses).
- **FR-018**: The interview MUST also support text input as a fallback for candidates who cannot
  use voice.
- **FR-019**: The AI MUST ask questions that probe each evaluation dimension defined in the job
  criteria, adapting follow-up questions based on the candidate's responses.
- **FR-020**: The interview MUST end when all evaluation dimensions have been adequately explored
  or a maximum turn count is reached.
- **FR-020a**: If a session is interrupted (network drop, browser close, or similar), the candidate
  MUST be able to reconnect and resume from the last completed turn within 24 hours of the
  interruption. After 24 hours, the session expires and cannot be resumed; the candidate's
  partial transcript is retained for any completed turns.
- **FR-020b**: If the AI agent service is unavailable mid-interview, the system MUST immediately
  surface a clear error message to the candidate explaining the disruption; the session MUST be
  preserved as resumable within the same 24-hour window so the candidate can reconnect when the
  service recovers. The interruption MUST be distinguishable from candidate abandonment in the
  recruiter's view.
- **FR-021**: The full interview transcript MUST be stored with each turn attributed to either the
  candidate or the AI.
- **FR-022**: Audio recordings of each turn MUST be stored and retrievable by recruiters.
- **FR-023**: System MUST detect and block harmful, off-topic, or manipulative candidate inputs;
  blocked turns MUST NOT be stored as content.

**Evaluation**

- **FR-024**: System MUST automatically generate an evaluation report after each completed
  interview, including: an overall score, a hire/no-hire recommendation, and per-dimension scores.
- **FR-025**: Each dimension score MUST include at least one supporting quote from the interview
  transcript as evidence.
- **FR-026**: System MUST identify and flag inconsistencies between claims made in the CV and
  statements made during the interview.
- **FR-027**: System MUST score communication quality: response depth, use of filler words, and
  frequency of topic deflection.
- **FR-028**: System MUST flag evaluations where the overall quality of evidence is below a
  confidence threshold, indicating the result may require human review.
- **FR-029**: Recruiters MUST be able to view a ranked list of all evaluated candidates for a job,
  ordered by overall score.
- **FR-030**: Recruiters MUST be able to view the full evaluation detail and transcript for any
  candidate, including audio playback.

**Candidate Feedback**

- **FR-031**: Candidates MUST receive an automated feedback email once their evaluation is
  complete.
- **FR-032**: Candidates MUST be able to access a feedback report via a secure token link with no
  account required.
- **FR-033**: The feedback report MUST display per-dimension scores and a written summary of
  strengths and areas for improvement.

### Key Entities *(include if feature involves data)*

- **Company**: A hiring organization using HireIQ; all data belongs to a company and is isolated
  from other companies.
- **User**: A recruiter or admin belonging to a company; authenticated with email and password.
- **Job Posting**: A role a company is hiring for; moves through draft → setup → active → closed
  states.
- **Job Criteria**: The structured evaluation framework for a job — required skills, experience
  level, evaluation dimensions with weights, and dealbreakers; produced by the setup conversation.
- **Candidate**: A person applying for a job; identified globally by email but associated to a
  company through their applications.
- **Application**: A candidate's submission for a specific job; contains CV content, screening
  score, and status.
- **Interview Session**: A structured AI-conducted interview for one application; stores mode
  (voice/text), status, and timing.
- **Interview Message**: A single turn in an interview — either candidate speech/text or AI
  response; includes transcript content and optional audio reference.
- **Evaluation**: The AI-generated assessment of a candidate's interview; includes overall score,
  recommendation, dimension scores, consistency flags, and communication metrics.
- **Audit Log**: An immutable record of all significant platform actions (applications, interview
  events, evaluation results, security events) for compliance and debugging purposes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A recruiter can complete job setup — from creating the posting to the job being
  active — in under 15 minutes.
- **SC-002**: CV screening results (score, rationale, status) are available within 2 minutes of
  CV upload for 95% of applications.
- **SC-003**: A candidate can complete a full voice interview in under 30 minutes.
- **SC-004**: Evaluation reports are available within 5 minutes of interview completion.
- **SC-005**: 100% of companies' data is isolated — no candidate, application, or evaluation data
  from one company is accessible to another company's users under any circumstances.
- **SC-006**: All AI-generated outputs stored to the system have had personal identifiers removed
  before storage; no raw PII appears in stored evaluation or transcript records.
- **SC-007**: 90% of completed interviews produce an evaluation that passes quality confidence
  checks and does not require a low-confidence flag.
- **SC-008**: Recruiters report that the shortlist view and evaluation detail give them enough
  information to make a hire/no-hire decision without reviewing additional materials in 80% of
  cases.

## Assumptions

- Candidates have access to a device with a working microphone and a modern web browser to
  participate in voice interviews.
- CV files are submitted as PDFs only; other file formats (DOCX, images) are out of scope for MVP.
- Each job has one standard interview template driven by its criteria; per-candidate question
  customization beyond adaptive follow-up is out of scope for MVP.
- The platform supports English-language CVs and interviews only for MVP; multi-language support
  is deferred to V2.
- A candidate who applies to two different jobs (even at the same company) is treated as two
  independent applications with separate screening and interview sessions.
- Compliance with specific hiring regulations (GDPR, EEOC, CCPA) is a future concern; the
  platform is designed with data isolation and PII redaction to support compliance but is not
  certified for MVP.
- Email notifications are transactional (confirmation, invitation, feedback) and do not require
  marketing opt-in.
- Automated evaluations are decision-support tools — final hiring decisions remain with the
  recruiter and are never made solely by the system.

## Clarifications

### Session 2026-06-04

- Q: How long should the interview invitation link remain valid? → A: 7 days after sending.
- Q: What happens when a candidate uploads a corrupted or password-protected PDF? → A: Reject upload immediately with a clear error; prompt candidate to re-upload; no application created.
- Q: What happens when an interview session is interrupted mid-way? → A: Resume within 24 hours from last completed turn; after 24 hours the session expires.
- Q: What determines whether a candidate is "qualified" after CV screening? → A: Recruiter sets a minimum score threshold (0–100) per job during setup; candidates at or above it are qualified.
- Q: What happens when the AI service is unavailable mid-interview? → A: Surface a clear error to the candidate; preserve session as resumable within the 24-hour window; distinguish system interruption from candidate abandonment in recruiter view.
- Q: How long does the candidate feedback token remain valid? → A: 30 days from the date the evaluation is completed.
- Q: Is there a rate limit on CV uploads? → A: Yes — maximum 5 CV uploads per IP address per hour to prevent abuse. Candidates exceeding the limit receive a 429 response with a clear message to try again later.
