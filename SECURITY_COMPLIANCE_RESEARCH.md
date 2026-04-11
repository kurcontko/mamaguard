# Security & Compliance Research: Healthcare AI Agents (A2A/MCP/FHIR)

*Compiled April 7, 2026 -- for the Agents Assemble Hackathon*

---

## 1. HIPAA Requirements for Agent-to-Agent Communication

### 1.1 What Makes Inter-Agent Communication HIPAA-Compliant

Under the 2025 HIPAA Security Rule amendments (effective February 16, 2026), AI agents that access, process, or transmit PHI are subject to the same obligations as human employees. Key requirements include:

- **Encryption in transit and at rest**: All inter-agent communication carrying PHI must use TLS 1.2+ (45 CFR 164.312(e)(1)). Data at rest must be encrypted with AES-256 or equivalent.
- **Access controls**: Each agent must have a unique identity and authentication credentials. Role-based or attribute-based access controls must limit each agent to only the data it needs (45 CFR 164.312(a)(1)).
- **AI-specific risk analysis**: The 2026 HIPAA updates explicitly require covered entities to perform risk analyses specific to AI systems, addressing hallucination risk, prompt injection risk, training data leakage, and scope-of-action risk.
- **Audit logging**: Every agent action involving PHI must be logged -- who accessed what, when, and for what purpose (45 CFR 164.312(b)). The 2025 amendments add a 72-hour breach notification requirement and mandatory vulnerability scanning every 6 months.

**Reference**: HHS OCR, "HIPAA Security Rule Updates: AI System Requirements," 2025; 45 CFR Parts 160, 164.

### 1.2 What Counts as PHI in FHIR Data

Under HIPAA, PHI is any individually identifiable health information. In FHIR, this includes virtually all patient-linked resources:

- **Patient**: name, address, DOB, SSN, MRN -- all direct identifiers
- **Observation, Condition, MedicationRequest, Procedure**: clinical data linked to a patient
- **Encounter, AllergyIntolerance, DiagnosticReport, ImagingStudy**: all PHI when linked to a patient reference
- **Practitioner data**: generally NOT PHI (unless acting as a patient)
- **De-identified data**: If data meets HIPAA Safe Harbor (18 identifiers removed) or Expert Determination standards, it is not PHI

**Critical for hackathon**: The hackathon rules mandate use of **synthetic or de-identified data only**. No real PHI is permitted. This eliminates most HIPAA compliance burden for the hackathon submission itself, but you should still architect as if real PHI were flowing.

### 1.3 Business Associate Agreements (BAAs)

When agents are hosted on different infrastructure:

- Each infrastructure provider that processes PHI is a **Business Associate** and needs a signed BAA with the Covered Entity.
- If Agent A (hosted on AWS) sends PHI to Agent B (hosted on Azure), both AWS and Azure need BAAs with the covered entity, AND the operator of Agent B may need a BAA as a subcontractor/business associate.
- The 2026 HIPAA updates strengthen BAA requirements to specifically address **AI-related obligations**: model governance, data handling for inference, audit logging for agent actions, and AI-specific incident response procedures.
- **Prompt Opinion**: Their Terms of Service (Section 1.7) explicitly state they will act as a Business Associate and execute a BAA if you submit PHI. However, PHI use is **by invitation only** during their preview period -- general use does not include PHI.

**Reference**: 45 CFR 164.502(e), 164.504(e); Prompt Opinion Terms of Service Section 1.7-1.8.

### 1.4 Minimum Necessary Rule

The Minimum Necessary Rule (45 CFR 164.502(b)) requires that only the minimum amount of PHI needed for a specific purpose be shared. For multi-agent systems:

- **Scope FHIR queries narrowly**: Instead of requesting `patient/*.rs` (all resources), request only the specific resource types needed (e.g., `patient/Observation.rs?category=laboratory`).
- **Filter before forwarding**: An orchestrating agent should strip unnecessary fields before passing data to downstream agents.
- **Use SMART on FHIR scopes**: Scopes are the primary enforcement mechanism -- request only `patient/Condition.rs` if only conditions are needed, not `patient/*.cruds`.
- **Design agent tool descriptions narrowly**: Each MCP tool should request only the data it specifically needs.

**Reference**: 45 CFR 164.502(b); Foley & Lardner LLP, "HIPAA Compliance for AI in Digital Health," May 2025.

### 1.5 Audit Trail Requirements

- Log every agent access to PHI: agent identity, timestamp, resources accessed, action taken, purpose
- Logs must be tamper-proof and retained for minimum 6 years (HIPAA) or longer per state law
- The 2025 Security Rule amendments made network segmentation mandatory and added 72-hour breach notification
- For multi-agent systems, each agent should maintain its own audit log, and the orchestrating platform should maintain a composite audit trail
- Prompt Opinion's platform terms (Section 1.8) commit to breach notifications "without unreasonable delay"

---

## 2. SMART on FHIR + OAuth Security Model

### 2.1 SMART on FHIR Scopes, Consent, and Authorization

SMART on FHIR (v2.2.0) uses OAuth 2.0 scopes to control access. Key scope categories:

| Scope Pattern | Meaning |
|---|---|
| `patient/[Resource].cruds` | Patient-specific access (c=create, r=read, u=update, d=delete, s=search) |
| `user/[Resource].cruds` | User-level access (based on logged-in user's permissions) |
| `system/[Resource].cruds` | System-level access (backend services, no user in loop) |
| `launch/patient` | Request patient context at launch |
| `openid fhirUser` | Get identity of current user |
| `offline_access` | Request refresh token |

**Granular scopes** (SMART v2.0+): You can add search parameter constraints, e.g., `patient/Observation.rs?category=laboratory` to limit to lab observations only.

**Wildcard scopes** (`patient/*.cruds`): Grant access to ALL resource types -- use sparingly and only when truly needed. Authorization servers may grant narrower scopes than requested.

**Reference**: HL7 SMART App Launch v2.2.0, https://build.fhir.org/ig/HL7/smart-app-launch/scopes-and-launch-context.html

### 2.2 Token Flow in Multi-Agent Scenarios

Multi-agent healthcare AI creates a token management challenge. Several approaches exist:

1. **Token Pass-Through (SHARP model)**: The orchestrating agent acquires a FHIR access token and passes it to downstream MCP servers via HTTP headers (`X-FHIR-Access-Token`). The MCP server uses this token to query the FHIR server directly. This is the approach SHARP on MCP uses.

2. **OAuth Token Exchange (RFC 8693)**: An agent can exchange one token for another with potentially different scopes, suitable for delegation chains. The original token is exchanged at the authorization server for a new, potentially narrower token.

3. **OAuth Scope Aggregation (IETF draft-jia-oauth-scope-aggregation-00, Feb 2026)**: A new IETF draft specifically for multi-step AI agent workflows. An agent pre-computes all needed scopes across a workflow, requests a single aggregated authorization, and avoids repeated consent prompts. Key features:
   - Resource metadata includes a `security` member advertising required scopes
   - Agent aggregates scopes per authorization domain
   - Single user consent per authorization domain
   - Token downscoping (RFC 8693) recommended after completing each workflow step
   - Sender-constrained tokens (DPoP, RFC 9449) recommended to prevent token replay

4. **SMART Backend Services**: For system-to-system communication without a user in the loop, uses client credentials grant with signed JWTs.

**Reference**: IETF draft-jia-oauth-scope-aggregation-00 (Feb 2026); RFC 8693 (Token Exchange); SMART App Launch Backend Services.

### 2.3 SMART Permission Tickets (Argonaut Project, March 2026)

Josh Mandel announced the Argonaut SMART Permission Tickets project on March 24, 2026. This is a new standard for **portable, verifiable authorization**:

**Problem it solves**: Today, if a patient wants to use an app to aggregate data from 5 health systems, they must complete 5 separate OAuth flows. For system-to-system access, there's no standard way to scope backend service access to specific patients.

**How it works**:
- A **Permission Ticket** is a cryptographically signed JWT that encodes authorization decisions in a portable form
- It rides alongside standard SMART Backend Services client assertions
- A trusted issuer (identity service, hospital, etc.) mints a signed ticket scoped to specific patients, data types, or date ranges
- The ticket is presented to SMART token endpoints at multiple hospitals, which validate the signature and issue standard access tokens

**Example Permission Ticket payload**:
```json
{
  "iss": "https://trusted-issuer.example.com",
  "aud": "https://fhir.hospital.com",
  "ticket_type": "https://smarthealthit.org/permission-ticket-type/public-health-investigation-v1",
  "authorization": {
    "subject": {"type": "reference", "reference": "Patient/123"},
    "access": {"scopes": ["patient/*.rs"]}
  },
  "details": {
    "condition": "111852003",
    "case": "local-case-id-8899"
  }
}
```

**Use cases**: Patient data aggregation across health systems, public health follow-up, caregiver delegation.

**Status**: Early-stage specification work. The Argonaut community is scoping requirements and exploring technical tradeoffs. Not yet implementable for hackathon, but worth mentioning in architecture discussions.

**Reference**: Josh Mandel, MD, "SMART Permission Tickets: Argonaut Launch!" LinkedIn, March 24, 2026.

---

## 3. SHARP Extension Specs Security

### 3.1 How SHARP Handles FHIR Credentials

SHARP (Standardized Healthcare Agent Remote Protocol) on MCP passes healthcare context via HTTP headers in a CDS Hooks-style pattern:

| Header | Purpose |
|---|---|
| `X-FHIR-Server-URL` | URL of the FHIR server to connect to |
| `X-FHIR-Access-Token` | OAuth access token for the FHIR server |
| `X-Patient-ID` | (Optional) Patient ID in context |

**Flow**: The calling agent (or host platform like Prompt Opinion) already has authentication with the FHIR server via SMART on FHIR. It passes these credentials to the MCP server, which uses them to query the FHIR server on behalf of the user.

**FHIR Context Discovery**: MCP servers advertise whether they need FHIR context via the `initialize` response: `$.capabilities.experimental.fhir_context_required.value` (boolean). If `true`, the client must include the headers. Missing required headers result in 403 Forbidden.

**Reference**: https://sharponmcp.com/key-components.html

### 3.2 Security Risks of Token-in-Header Approach

Passing access tokens in custom HTTP headers between services introduces several risks:

1. **Token exposure in logs**: HTTP headers are frequently logged by web servers, proxies, and load balancers. Access tokens in headers may end up in plaintext logs. **Mitigation**: Configure infrastructure to redact `X-FHIR-Access-Token` from all logs.

2. **Token replay**: If a token is intercepted, it can be replayed by an attacker. **Mitigation**: Use short-lived tokens, DPoP (RFC 9449) for sender-constrained tokens, and TLS everywhere.

3. **Overly broad token scope**: The MCP server receives whatever scopes the token carries, which may be broader than needed. **Mitigation**: Mint narrow-scope tokens specifically for each MCP server invocation.

4. **No token binding to MCP server**: The same token could be forwarded to multiple MCP servers. **Mitigation**: Token exchange (RFC 8693) to create per-server tokens.

5. **Header injection**: If header values are not properly validated, they could be exploited. **Mitigation**: Strict input validation on all header values.

6. **Trust boundary crossing**: The token crosses from the agent's trust domain into the MCP server's trust domain. The MCP server operator can use the token for any action within its scope. **Mitigation**: BAAs, audit logging, narrow scopes.

### 3.3 SHARP Authentication for MCP Servers

SHARP supports four authentication models for the MCP server connection itself (separate from the FHIR token):

1. **Anonymous access**: No client authentication required to connect to the MCP server. The server may still require FHIR context headers to function.
2. **OAuth Client Credentials**: Standard OAuth 2.0 client credentials grant, with optional dynamic client registration.
3. **API Key**: Simple API key-based authentication.
4. **Basic Authentication**: Username/password via HTTP Basic Auth.

For the hackathon, anonymous access is likely sufficient for community MCP servers. Production deployments should use OAuth Client Credentials.

**Reference**: https://sharponmcp.com/key-components.html

---

## 4. FDA / Regulatory Considerations

### 4.1 Is a Clinical Decision Support AI Agent a Medical Device?

**It depends on the 21st Century Cures Act Section 3060(a) criteria.** The FDA's January 2026 CDS Guidance (final) clarifies four criteria that must ALL be met for CDS software to be excluded from device regulation ("Non-Device CDS"):

1. **Not intended to acquire, process, or analyze a medical image, signal, or pattern**
2. **Intended for the purpose of displaying, analyzing, or printing medical information**
3. **Intended for use by a healthcare professional (HCP)**
4. **Intended to enable the HCP to independently review the basis for the recommendation** (the "transparency" criterion)

If ALL four are met, the software is **not a medical device** and not subject to FDA premarket review.

**Key implications for AI agents**:
- If your agent provides **recommendations that an HCP can independently review** (shows its reasoning, cites sources, presents evidence), it likely qualifies as Non-Device CDS
- If your agent provides **opaque recommendations** where the HCP cannot review the basis (black-box AI), it IS a medical device
- If your agent is **patient-facing** (not HCP-facing), it IS a medical device regardless of transparency
- If your agent **autonomously takes clinical actions** without HCP review, it IS a medical device

**For the hackathon**: Design your agent as a clinical decision **support** tool that presents recommendations with citations and reasoning to an HCP. Avoid autonomous clinical decision-making. This keeps you in Non-Device CDS territory.

**Reference**: FDA, "Clinical Decision Support Software: Guidance for Industry," January 29, 2026; 21st Century Cures Act Section 3060(a); FD&C Act Section 520(o)(1)(E).

### 4.2 21st Century Cures Act & Information Blocking

The Cures Act and ONC's HTI rules (HTI-1 final, HTI-5 proposed December 2025) are directly relevant:

- **Information Blocking prohibition**: Healthcare providers, health IT developers, and HIEs cannot block access to electronic health information (EHI). This supports the case for AI agent interoperability.
- **HTI-5 (proposed Dec 2025)**: Includes provisions addressing AI agents as EHR users. A regulatory battle is underway (per Josh Mandel's March 2026 analysis) over whether AI agents acting autonomously should have the same API access rights as human users.
- **TEFCA (Trusted Exchange Framework)**: ONC's framework for nationwide interoperability includes Facilitated FHIR Implementation, requiring SMART on FHIR and OIDC support.
- **Certified Health IT**: Must support FHIR R4 APIs and SMART App Launch for patient and provider access (per HTI-1).

**Reference**: ONC HTI-1 Final Rule; ONC HTI-5 Proposed Rule (Dec 2025); NEJM, "The Next Chapter in Health Care Interoperability," Feb 2026.

### 4.3 FDA's AI/ML Guidance Landscape (2024-2026)

- **AI/ML SaMD Action Plan** (ongoing): FDA tracks authorized AI/ML-enabled medical devices (1,000+ by 2025)
- **January 2025**: FDA issued first definitive guideline on AI to support regulatory decision-making for drugs
- **January 6, 2026**: Updated CDS Final Guidance and General Wellness Final Guidance
- **January 29, 2026**: Superseding CDS guidance with additional clarifications
- **February 2026**: Digital Health Devices Pilot ("Technology-Enabled Meaningful Patient Outcomes")
- **Predetermined Change Control Plans**: FDA allows manufacturers to describe planned AI model updates in advance, reducing regulatory burden for iterative ML improvements

**Reference**: FDA Digital Health Center of Excellence; FDA, "Artificial Intelligence in Software as a Medical Device," updated March 2025.

---

## 5. Data Residency & Sovereignty

### 5.1 Where Can Healthcare Data Be Processed?

- **United States**: HIPAA does not explicitly restrict data to US soil, but practical considerations and many state laws create strong pressures to keep data domestic. The 2025 HIPAA Security Rule amendments emphasize network segmentation and access controls that effectively require knowing where data is processed.
- **EU (if applicable)**: GDPR requires lawful basis for processing, data protection impact assessments, and restrictions on transfers outside the EU/EEA (Schrems II implications).
- **State laws**: California AB 489 (effective Jan 1, 2026) adds AI-specific disclosure and transparency requirements. 10+ states have similar bills pending.

**For the hackathon**: Since you're using synthetic data, residency is not a hard constraint. But design your architecture assuming US-only processing.

### 5.2 Cloud Provider Requirements

To process PHI in the cloud, the cloud provider must:
- Sign a BAA (AWS, Azure, GCP all offer these)
- Use only **HIPAA-eligible services** (not all services qualify)
- Key HIPAA-eligible services:
  - **AWS**: EC2, S3, Lambda, RDS, ECS, Fargate, API Gateway, CloudWatch, SageMaker (with conditions)
  - **Azure**: App Service, Functions, Cosmos DB, SQL Database, Blob Storage, Azure AI Services
  - **GCP**: Compute Engine, Cloud Functions, Cloud SQL, BigQuery, Cloud Healthcare API, Vertex AI
- Encryption keys must be managed appropriately (AWS KMS, Azure Key Vault, GCP Cloud KMS)
- Audit logging must be enabled (CloudTrail, Azure Monitor, Cloud Audit Logs)

**Reference**: AWS HIPAA Eligible Services; Azure HIPAA/HITRUST compliance documentation; GCP Healthcare compliance.

---

## 6. Prompt Opinion Platform Security

### 6.1 Platform Security Guardrails

Based on Prompt Opinion's Terms of Service (effective March 1, 2026):

- **No PHI by default**: General use does not include PHI. PHI requires invitation + executed BAA (Section 1.7).
- **BAA available**: They will act as Business Associate for covered entities that execute a BAA (Section 1.7).
- **HIPAA safeguards**: For PHI under BAA, they implement Security Rule safeguards, follow minimum necessary standard, and provide breach notifications (Section 1.8).
- **De-identified data**: They may create and use de-identified data meeting HIPAA standards for analytics and product development, and will not attempt re-identification or sell/lease such data (Section 1.9).
- **Prohibited uses**: Autonomous clinical decision-making, emergency/life-support scenarios, and using Service output as medical advice are explicitly prohibited (Section 1.3, 1.5, 1.6).
- **AI output disclaimers**: Outputs may be inaccurate. Users must verify against clinical standards (Section 1.10).
- **US-based service**: Controlled and operated from US facilities (Section 10.3).

### 6.2 How Prompt Opinion Handles PHI in Agent Communications

- **Preview Period**: Currently in preview/beta. PHI use is by invitation only.
- **Hackathon rules explicitly prohibit PHI**: "The project must exclusively use synthetic or de-identified data (No PHI). Submissions that are not published in the Marketplace or fail to demonstrate integration within Prompt Opinion will not proceed to Stage Two."
- **Marketplace validation**: Stage One judging includes "Safety Compliance" check -- projects must use synthetic/de-identified data only.
- **Agent communications within the platform**: SHARP headers pass FHIR context between agents/MCP servers. The platform acts as the orchestration layer. With a BAA in place, the platform promises Security Rule safeguards. Without a BAA, no PHI should flow through the platform.

**Reference**: Prompt Opinion Terms of Service (March 1, 2026); Agents Assemble Official Rules (devpost.com).

---

## 7. Practical Implications for the Hackathon

### Must Do
1. **Use only synthetic/de-identified data** -- this is a hard rule for disqualification
2. **Design for HCP-in-the-loop** -- show reasoning and sources to stay in Non-Device CDS territory
3. **Implement SHARP headers** (X-FHIR-Server-URL, X-FHIR-Access-Token, X-Patient-ID) for FHIR-backed MCP servers
4. **Publish to Prompt Opinion Marketplace** with functional configuration

### Should Do
5. **Use narrow SMART on FHIR scopes** rather than wildcards -- demonstrates Minimum Necessary compliance
6. **Log all agent actions** -- even with synthetic data, showing an audit trail demonstrates compliance awareness
7. **Use TLS everywhere** for inter-agent communication
8. **Validate and sanitize inputs** to prevent prompt injection

### Nice to Have (Differentiators)
9. **Implement token downscoping** when forwarding tokens to downstream agents
10. **Show FHIR context discovery** in your MCP server's initialize response
11. **Reference SMART Permission Tickets** as a future-looking authorization approach
12. **Address the AI-specific risk categories** from the 2026 HIPAA updates (hallucination mitigation, prompt injection defense)

---

## Sources

- HHS OCR, "HIPAA Security Rule Updates: AI System Requirements," 2025
- 45 CFR Parts 160, 164 (HIPAA Privacy and Security Rules)
- FDA, "Clinical Decision Support Software: Guidance for Industry," January 29, 2026
- 21st Century Cures Act, Section 3060(a)
- HL7 SMART App Launch v2.2.0: https://build.fhir.org/ig/HL7/smart-app-launch/scopes-and-launch-context.html
- IETF draft-jia-oauth-scope-aggregation-00, February 2026
- SHARP on MCP Specification: https://sharponmcp.com
- Josh Mandel, MD, "SMART Permission Tickets: Argonaut Launch!" LinkedIn, March 24, 2026
- Prompt Opinion Terms of Service: https://www.promptopinion.ai/terms-of-service
- Agents Assemble Official Rules: https://agents-assemble.devpost.com/rules
- Ajentik, "Navigating HIPAA Compliance for AI Agents in Healthcare," February 2026
- Kiteworks, "AI Agents and HIPAA: Solving the PHI Access Challenge," March 2026
- ONC HTI-1 Final Rule; HTI-5 Proposed Rule (December 2025)
- California Assembly Bill 489, "Healthcare AI Transparency Act," effective January 1, 2026
- RFC 8693 (OAuth Token Exchange), RFC 9449 (DPoP), RFC 6749 (OAuth 2.0)
