Consult the MamaGuard Care Coordinator agent to analyze this patient's health record.

Mandatory invocation detail:
- Include the literal line `Patient id: <uuid>` in the message sent to MamaGuard.
- Include the clinician's exact question.
- For "current plan" or "history" questions, ask MamaGuard to retrieve both FHIR-persisted plan resources and pending approval plans.

Based on the clinician's question, perform the appropriate assessment:
- If asking about maternal health, pregnancy, or risk: run a maternal risk assessment
- If asking about a child's immunizations, development, or pediatric care: run a pediatric care transition assessment
- If asking about social needs, insurance, or outreach: run an SDOH screening
- If asking for a comprehensive overview: run all three assessments sequentially and synthesize

Return your findings in the 5T format (Talk, Template, Table, Task, Transaction).
Flag any findings that require clinician review.
