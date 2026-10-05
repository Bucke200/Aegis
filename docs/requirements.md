# Requirements Document

## Introduction

The Aegis VIP Threat & Misinformation Monitoring Platform is a near-real-time intelligence system that protects Very Important Persons (VIPs) from online threats, impersonation, data leaks, and misinformation campaigns. It collects content from social platforms, messaging channels, and paste/code sites through compliant access methods. It analyzes that content with a cascade of rule-based and ML detectors and turns the results into scored, evidence-backed incidents that analysts triage on a live dashboard.

### Scope

- **MVP:**
  - Sources: replay/synthetic data, manual URL submission, Telegram public channels, and GitHub code search.
  - Detection: text threat detection (English, Hindi, Hinglish), impersonation, media matching with OCR, leak/PII detection, and coordinated campaign detection.
  - Platform: scoring, evidence capture, email and Slack alerts, the incident workflow, and the analyst feedback loop.
- **Post-MVP:**
  - Sources: X, Meta owned-account and hashtag monitoring, YouTube, Discord, and Pastebin.
  - Alerts: SMS.
  - Detection: synthetic-media (deepfake) detection and a fine-tuned threat classifier.
  - Infrastructure: Elasticsearch, a graph database, and Kubernetes.
- **MVP release** means Phases 0–3 of the implementation plan are complete. Phase 1 (the vertical slice) is an internal milestone, not a release.

### Assumptions (to validate with stakeholders)

- **Scale:** up to 50 VIPs and 200,000 collected items/day (about 2.3 items/second on average).
  - **Sustained design rate:** 10 items/second (about 4× the average). Latency targets are measured at this rate.
  - **Burst:** 50 items/second for up to 15 minutes (e.g., a viral event). Queues absorb bursts; the system must recover within 10 minutes after a burst ends.
- **Users:** up to 20 concurrent analyst users.
- **Languages:** English, Hindi (Devanagari and romanized), and code-mixed Hindi-English. Other Indic languages are post-MVP.

### Glossary

- **Item:** a single collected piece of content (post, comment, message, paste, code file).
- **Account:** an author identity on a source platform.
- **Official account:** a VIP-owned account registered and verified in the system.
- **Detection:** the output of one detector on one item.
- **Incident:** an analyst-facing record built from one or more detections on an item.
- **Campaign:** a group of items and accounts judged to be coordinated.
- **Processing latency:** time from an item's `collected_at` to the corresponding incident being visible on the dashboard.

## Requirements

### Requirement 1: VIP Profile Management

**User Story:** As an administrator, I want to register each VIP with their identities and reference material, so that detectors know whom to protect and what "genuine" looks like.

#### Acceptance Criteria

1. WHEN an administrator creates or edits a VIP THEN the system SHALL store name, aliases, spelling/transliteration variants, monitoring keywords, and disambiguation context keywords
2. WHEN official accounts are registered THEN the system SHALL store platform, handle, platform account ID, and verification evidence, AND SHALL exclude those accounts from impersonation flags
3. WHEN reference images (portraits, avatars, official media) are uploaded THEN the system SHALL compute and store perceptual hashes and image embeddings for later comparison
4. WHEN sensitive VIP data (phone numbers, email addresses, home address) is registered for leak detection THEN the system SHALL store only salted hashes/fingerprints of normalized values, never plaintext
5. WHEN monitoring is paused for a VIP THEN the system SHALL stop creating new incidents for that VIP within 5 minutes while retaining existing incidents
6. WHEN any VIP configuration changes THEN the system SHALL record who changed what, and when, in the audit log

### Requirement 2: Data Ingestion

**User Story:** As a security analyst, I want content collected from every platform where threats appear, through methods that are legal and sustainable, so that coverage doesn't disappear when a platform blocks us.

#### Acceptance Criteria

1. WHEN monitoring is active THEN the system SHALL collect items from each enabled source using only the access method documented for that source in the design's source access matrix
2. The system SHALL support, at MVP, a replay source for recorded or synthetic datasets, manual URL submission, Telegram public channels, and GitHub code search
3. The system SHALL be extensible to post-MVP sources (X, Facebook/Instagram owned accounts and hashtags, YouTube comments, Discord invited servers, Pastebin) by adding a connector without changes to downstream components
4. WHEN a source returns a rate-limit response THEN the connector SHALL back off according to the platform's reset information AND SHALL NOT exceed the platform's documented limits
5. WHEN a source's terms prohibit automated collection THEN the system SHALL NOT collect from it automatically and SHALL rely on manual URL submission instead
6. WHEN an analyst submits a URL of a post or a profile THEN the system SHALL fetch, normalize, and analyze it through the same pipeline as automatically collected items and accounts
7. WHEN a connector fails authentication or produces no data for longer than its configured staleness window THEN the system SHALL raise an operational alert and mark the source as degraded
8. WHEN an item is collected THEN the system SHALL record `collected_at` and, where available, the platform's `posted_at`

### Requirement 3: Normalization and Deduplication

**User Story:** As a security analyst, I want every item in one consistent format with duplicates removed, so that I never triage the same post twice.

#### Acceptance Criteria

1. WHEN an item is collected THEN the system SHALL convert it to the versioned common item schema while retaining the original raw payload
2. WHEN an item fails schema validation THEN the system SHALL route it to a dead-letter queue with the validation error AND SHALL NOT drop it silently
3. WHEN an item with the same (source, platform item ID) has already been processed THEN the system SHALL update its engagement metadata AND SHALL NOT create a duplicate incident
4. WHEN an edit or deletion of a previously collected item is observed THEN the system SHALL keep the originally captured version and record the change with a timestamp
5. WHEN normalizing an item THEN the system SHALL detect and record its language and script

### Requirement 4: VIP Mention Resolution

**User Story:** As a security analyst, I want the system to work out which VIP a post is actually about, including misspellings and Hinglish, so that coverage is complete without drowning me in name collisions.

#### Acceptance Criteria

1. WHEN an item is processed THEN the system SHALL identify referenced VIPs using names, aliases, transliteration variants, handles, and tags
2. WHEN text is romanized Hindi or code-mixed THEN the system SHALL match aliases after transliteration normalization
3. WHEN an item references multiple VIPs THEN the system SHALL associate it with each of them
4. WHEN a matched name is ambiguous THEN the system SHALL use the VIP's context keywords to disambiguate AND SHALL record a match confidence

### Requirement 5: Text Threat Detection

**User Story:** As a security analyst, I want threats separated from ordinary criticism, so that I spend time on real danger rather than negative opinion.

#### Acceptance Criteria

1. WHEN analyzing text THEN the system SHALL classify threat intent as exactly one of these canonical labels, used verbatim in storage, UI, and evaluation: `none`, `criticism`, `harassment` (abuse or harassment), `violent_threat`, `incitement`, `doxxing`. This classification SHALL be separate from sentiment
2. WHEN analyzing text THEN the system SHALL support English, Hindi (Devanagari and romanized), and code-mixed Hindi-English
3. WHEN the first-stage filter scores an item below its configured threshold THEN the system SHALL skip later, more expensive stages for that item
4. WHERE the LLM stage is enabled, WHEN an item passes the first-stage filter and the daily cost budget is not exhausted THEN the system SHALL classify it with an LLM that returns structured output with a rationale. The daily budget SHALL be shared across all worker instances so that the same total applies regardless of how many run. WHERE a trained intent classifier is deployed (post-MVP), only items whose classifier score falls in the configured uncertainty band SHALL be sent to the LLM
5. WHEN a detection is produced THEN the system SHALL record detector name, model version, score, and the text spans that triggered it
6. WHEN no threat-class signal is present on an item (it expresses criticism, negativity, or toxicity without threat intent) THEN the system SHALL NOT create an incident above low severity, even when toxicity detectors fire

### Requirement 6: Impersonation Detection

**User Story:** As a communications strategist, I want fake profiles impersonating a VIP detected, explained, and packaged for reporting, so that takedowns happen quickly.

#### Acceptance Criteria

1. WHEN an account mentions, replies to, or resembles a VIP, including an account known only from its profile (e.g., a profile URL submitted by an analyst) THEN the system SHALL compute an impersonation score against that VIP's official accounts
2. WHEN comparing handles and display names THEN the system SHALL normalize Unicode confusables (homoglyphs), case, separators, and common character substitutions before computing similarity
3. WHEN scoring THEN the system SHALL combine handle similarity, display-name similarity, avatar similarity to reference images, bio similarity, and account metadata (age, follower/following ratio, verification status)
4. WHEN an account self-identifies as parody or fan THEN the system SHALL reduce its score and record the label
5. WHEN the score exceeds the VIP's configured threshold THEN the system SHALL produce an impersonation detection carrying every component score as evidence, which the scorer turns into an impersonation incident
6. WHEN an analyst confirms impersonation THEN the system SHALL generate a platform report package containing the account URL, captured evidence, and a side-by-side comparison with the official account
7. WHEN content soliciting money, payments, credentials, or personal information (e.g., payment handles, crypto wallet addresses, OTP or password requests, links to non-official domains) is found in a VIP-linked item THEN the system SHALL produce a solicitation detection, which SHALL take effect (weight and critical override) only when the item is attached to an impersonation incident, without waiting for analyst confirmation
8. WHEN an account is flagged for impersonating a VIP THEN the system SHALL keep one open impersonation incident per (account, VIP), attaching that account's later VIP-linked items to it instead of creating separate incidents
9. WHEN an item that already has its own incident is attached to an impersonation incident THEN the system SHALL merge the item incident into the impersonation incident: keep its history, notes, and assignee, stop scoring it separately, hide it from the default feed, link the two, and respect a prior False Positive decision on that item
10. WHEN a configuration change leaves an account with an open impersonation incident below the VIP's threshold THEN the system SHALL auto-resolve the incident with a system outcome of "below threshold" only if no analyst has acted on it, it is not critical, and no attached item scores medium or higher; otherwise it SHALL keep the incident open and flag it as below threshold for review

### Requirement 7: Media and Misinformation Analysis

**User Story:** As a communications strategist, I want repurposed or manipulated media identified with its original context, so that I can debunk it before it spreads.

#### Acceptance Criteria

1. WHEN an item contains images THEN the system SHALL compute perceptual hashes and an embedding and compare them with the VIP's reference media and previously seen media, regardless of whether the item already references a VIP by text, so that a VIP photo posted without naming the VIP is still linked
2. WHEN a match is found to media first seen in a different context (earlier date or different source) THEN the system SHALL flag possible repurposed media and show the earliest known occurrence
3. WHEN an image contains text THEN the system SHALL extract it with OCR (English and Devanagari) and pass it to text threat detection
4. WHEN an item contains video THEN the system SHALL extract keyframes and analyze them as images
5. WHEN an incident with media reaches high severity or above THEN the system SHALL run a reverse image search through a supported provider within a configured quota
6. WHERE synthetic-media detection is enabled THEN the system SHALL report its output as a labelled confidence signal AND SHALL NOT by itself mark media as fake

### Requirement 8: Leak and PII Exposure Detection

**User Story:** As a security analyst, I want to know as soon as a VIP's personal data or credentials appear publicly, so that we can act before it is used for harm.

#### Acceptance Criteria

1. WHEN a paste, code file, or post is analyzed THEN the system SHALL detect personal-data patterns (phone numbers, email addresses, government ID formats, postal addresses) and credentials or secrets
2. WHEN detected data matches a VIP's registered sensitive-data fingerprints THEN the system SHALL produce a fingerprint-match detection, which the scorer turns into a critical leak incident
3. WHEN detected personal data appears alongside a VIP mention but matches no fingerprint THEN the system SHALL produce a leak detection whose incident severity comes from the scoring engine
4. WHEN storing, displaying, or alerting on leak incidents THEN the system SHALL mask detected sensitive values for users without reveal permission AND SHALL log every reveal

### Requirement 9: Coordinated Campaign Detection

**User Story:** As a communications strategist, I want coordinated inauthentic behavior detected and mapped, so that I understand the scale and structure of an organized attack.

#### Acceptance Criteria

1. WHEN analyzing items about a VIP THEN the system SHALL cluster near-duplicate content using text similarity and media hash matches
2. WHEN a cluster contains at least N distinct accounts within a time window W THEN the system SHALL flag a candidate campaign, with N and W configurable per VIP (defaults: N = 10, W = 60 minutes)
3. WHEN monitoring mention volume THEN the system SHALL compare each VIP's hourly volume with that VIP's own rolling baseline and flag statistically anomalous spikes
4. WHEN evaluating a candidate campaign THEN the system SHALL weigh account signals (account age, creation-date clustering, posting cadence, shared avatars) AND SHALL exclude allowlisted accounts (e.g., verified news outlets) from cluster counts
5. WHEN a campaign is confirmed THEN the system SHALL record member accounts, items, timeline, and interaction edges, and SHALL provide a network visualization
6. WHEN new items match an open campaign THEN the system SHALL attach them to that campaign instead of creating a new one

### Requirement 10: Severity Scoring and Incident Creation

**User Story:** As a security analyst, I want one consistent, explainable severity for every incident, so that I can trust the ordering of my queue.

#### Acceptance Criteria

1. WHEN detections are produced for an item THEN the system SHALL compute a single risk score from detector scores, detector reliability weights, reach, VIP sensitivity, and VIP match confidence using the documented formula; for impersonation incidents it SHALL combine the account's impersonation score with the worst attached item's risk, so that posting volume alone does not raise severity
2. WHEN the risk score crosses configured band thresholds THEN the system SHALL assign severity low, medium, high, or critical
3. WHEN an override rule matches (a `violent_threat` with a location, time, or method; a fingerprint-match detection; or a solicitation detection) THEN the system SHALL assign critical severity regardless of the computed score
4. WHEN creating an incident THEN the system SHALL group all detections for the same item into one incident (or, for impersonation, the same account and VIP, per Req 6.8, merging any pre-existing incident for an attached item per Req 6.9) AND SHALL link it to an existing campaign where applicable
5. WHEN an incident is created THEN the system SHALL store a human-readable explanation of why it was flagged
6. WHEN scoring weights or thresholds change THEN the system SHALL version the scoring configuration and record which version scored each incident
7. WHEN an item joins a confirmed campaign, its reach grows by an order of magnitude, or its media analysis completes (adding OCR text, a reference-media link, or a repurposed-media finding) THEN the system SHALL re-score it, create an incident if the new score crosses the incident threshold, update the severity of an existing incident unless an analyst has set it manually, and record the re-score with its trigger

### Requirement 11: Real-Time Dashboard

**User Story:** As a security analyst, I want a live dashboard of incidents, so that I can identify and respond to threats quickly.

#### Acceptance Criteria

1. WHEN an incident is created or updated THEN the dashboard SHALL reflect the change without a page reload within 10 seconds
2. WHEN an incident is listed THEN the system SHALL show severity, VIP(s), platform, threat type(s), content snippet (or, for impersonation incidents, the suspect profile), masked where required, flagging reason, detection time, status, and assignee
3. WHEN I open the dashboard THEN the system SHALL list incidents in reverse-chronological order by default, with an option to sort by severity
4. WHEN I open an incident THEN the system SHALL show evidence, all detections and scores, account details, related incidents and campaign, status history, notes, and source links
5. WHEN a source is degraded THEN the dashboard SHALL display that source's status
6. The dashboard SHALL be usable at tablet and desktop widths

### Requirement 12: Search and Filtering

**User Story:** As a security analyst, I want to filter and search incidents on many criteria, so that I can focus on what matters for my current investigation.

#### Acceptance Criteria

1. WHEN using filters THEN the system SHALL allow filtering by VIP, threat type, severity, status, platform, assignee, campaign, language, and date range; the threat-type filter SHALL use the canonical taxonomy defined in the design (the six intent labels plus impersonation, solicitation, leak, repurposed media, and campaign)
2. WHEN searching THEN the system SHALL provide full-text search over item text, OCR-extracted text, and account names in all supported languages
3. WHEN multiple filters are applied THEN the system SHALL combine different filters with AND and multiple values within one filter with OR
4. WHEN results match a search THEN the system SHALL highlight the matching terms
5. WHEN searching across one year of data at the assumed scale THEN the system SHALL return results with p95 latency under 1 second
6. WHEN an analyst saves a search THEN the system SHALL store it for reuse

### Requirement 13: Evidence Collection and Integrity

**User Story:** As a security analyst, I want tamper-evident evidence for each incident, so that our proof holds up when escalated to platforms, legal counsel, or law enforcement.

#### Acceptance Criteria

1. WHEN an incident is created or re-scored at or above the configured capture severity (default: medium) THEN the system SHALL capture the raw payload, a rendered screenshot, original media, and a snapshot of the author account (for impersonation incidents: the suspect's profile page, avatar, and account snapshot, plus each attached item as it arrives)
2. WHEN capturing evidence THEN the system SHALL compute a SHA-256 hash for each artifact and produce a manifest containing the hashes, UTC capture time, source URL, and capturer version; when more evidence is captured for the same incident later, the system SHALL write a new manifest version chained to the previous one rather than modify it
3. WHEN storing evidence THEN the system SHALL use object storage with versioning and a write-once retention lock for the configured retention period; the lock SHALL be in governance mode so that deletion on retention expiry or VIP offboarding remains possible through a dedicated, audited retention role
4. WHEN evidence is viewed, downloaded, or exported THEN the system SHALL record the access in a chain-of-custody log
5. WHEN evidence is exported THEN the system SHALL produce a package (summary report, artifacts, manifest) that a third party can verify against the recorded hashes
6. WHEN rendering pages for capture THEN the system SHALL use an isolated, sandboxed browser that holds no analyst credentials, AND SHALL retry failed captures with backoff and record failures
7. WHEN the original content is later removed from the platform THEN the system SHALL keep the evidence accessible and mark the incident "source removed"

### Requirement 14: Alerting

**User Story:** As a security analyst, I want immediate, non-noisy notifications for serious threats, so that I can respond within minutes without suffering alert fatigue.

#### Acceptance Criteria

1. WHEN a critical incident is created at the sustained design rate THEN the system SHALL dispatch an alert within 2 minutes of the item's `collected_at` (p95)
2. The system SHALL support email and Slack alerts at MVP and SMS post-MVP
3. WHEN sending an alert THEN the system SHALL include a summary, severity, VIP, flagging reason, and a direct dashboard link, AND SHALL NOT include unmasked sensitive values
4. WHEN configuring alerts THEN the system SHALL support per-VIP and per-user severity thresholds, channels, and quiet hours, with quiet hours never suppressing critical alerts
5. WHEN an alert is sent THEN the system SHALL track delivery, retry failures with backoff, and escalate to a secondary recipient if a critical alert is not acknowledged within a configurable time
6. WHEN multiple related incidents (same campaign or account) occur within the grouping window THEN the system SHALL group them into one alert, and SHALL deliver configured lower severities as a periodic digest

### Requirement 15: Incident Workflow Management

**User Story:** As a security analyst, I want to manage incident status, ownership, and outcomes, so that my team coordinates response efficiently.

#### Acceptance Criteria

1. WHEN reviewing incidents THEN the system SHALL support statuses New, Under Review, Escalated, Resolved, and False Positive
2. WHEN a status changes THEN the system SHALL record the timestamp, user, and optional reason, and SHALL keep the full history
3. WHEN investigating THEN the system SHALL allow analysts to add notes to an incident
4. WHEN an incident is assigned THEN the system SHALL record the assignee and notify them
5. WHEN an analyst resolves an incident THEN the system SHALL require an outcome (e.g., reported to platform, taken down, referred to authorities, no action needed); automatic resolutions SHALL use a system-only outcome (e.g., "below threshold", Req 6.10)
6. WHEN tracking workflow THEN the system SHALL report time to acknowledge, time to resolve, and outcome distribution per VIP and team, with per-analyst metrics visible only to leads
7. WHEN incidents belong to a campaign THEN the system SHALL allow bulk status changes and assignment

### Requirement 16: Analyst Feedback and Detection Quality

**User Story:** As a team lead, I want analyst decisions to improve detection and every detector change to be measured, so that accuracy improves over time instead of drifting.

#### Acceptance Criteria

1. WHEN an analyst marks an incident False Positive or corrects its threat type or severity THEN the system SHALL store a label linked to the incident's subject (the item and its detections, or for impersonation incidents the account and its impersonation detection)
2. The system SHALL maintain a labelled evaluation set and report precision and recall per detector and per language
3. WHEN a detector, model, or threshold change is proposed THEN the system SHALL evaluate it against the evaluation set AND SHALL block deployment if precision or recall drops by more than a configured tolerance
4. WHEN viewing system metrics THEN the system SHALL show each detector's false-positive rate over time
5. WHEN an analyst creates an allowlist or suppression rule (e.g., a known satire account) THEN the system SHALL apply it with an expiry date and record it in the audit log

### Requirement 17: Access Control and Audit

**User Story:** As an administrator, I want role-based, VIP-scoped access with a full audit trail, so that sensitive intelligence is seen only by the right people.

#### Acceptance Criteria

1. WHEN anyone accesses the UI or API THEN the system SHALL require authentication, AND SHALL support multi-factor authentication for administrators
2. WHEN authorizing requests THEN the system SHALL enforce the roles Admin, Lead, Analyst, and Viewer, scoped to the VIPs a user is assigned to, AND SHALL gate revealing masked sensitive values on a separate per-VIP reveal permission that only Admins can grant and that Viewers can never hold
3. The system SHALL keep an append-only audit log of logins, configuration changes, status changes, evidence access, sensitive-value reveals, and exports
4. WHEN API clients exceed configured request rates THEN the system SHALL throttle them

### Requirement 18: Data Protection and Retention

**User Story:** As a data protection officer, I want collection and retention minimized and controlled, so that the platform complies with law and platform terms.

#### Acceptance Criteria

1. WHEN items are not linked to any VIP or incident THEN the system SHALL delete them after a configurable period (default 30 days)
2. WHEN retention for incidents and evidence expires (default 1 year) THEN the system SHALL delete them unless a legal hold is set
3. The system SHALL encrypt data in transit (TLS) and at rest (database and object storage)
4. WHEN monitoring of a VIP ends THEN the system SHALL support deletion of that VIP's data, including captured evidence through the audited retention role, excluding items under legal hold
5. The system SHALL document its purpose and lawful basis for processing and the terms-of-service review for each source, consistent with applicable law including India's Digital Personal Data Protection Act, 2023

### Requirement 19: Performance, Reliability, and Observability

**User Story:** As an operator, I want the platform to keep up with load, survive partial failures, and tell me when something is wrong.

#### Acceptance Criteria

1. WHEN ingesting at the sustained design rate (10 items/s) THEN queue depth SHALL NOT grow over any 30-minute window, AND WHEN a burst of up to 50 items/s lasting up to 15 minutes ends THEN all queues SHALL drain to their normal depth within 10 minutes
2. WHEN processing items at the sustained design rate THEN p95 processing latency SHALL be at most 60 seconds for text-only items and at most 5 minutes for items requiring media analysis
3. WHEN a single connector or worker fails THEN other sources and detectors SHALL continue operating, AND queued items SHALL survive service restarts
4. The system SHALL expose metrics for per-source ingest rate, queue depth, per-stage latency, detector error rate, and alert delivery success, plus structured logs and health endpoints for every service
5. WHEN queue backlog, connector staleness, dead-letter growth, or disk usage exceeds configured thresholds THEN the system SHALL raise an operational alert
6. The system SHALL have a documented, tested backup and restore procedure for the database and object storage, with an owner and agreed recovery-point and recovery-time objectives before the MVP release
