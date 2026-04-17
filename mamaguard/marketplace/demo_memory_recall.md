# Memory Recall Demo — The MamaGuard Differentiator

**For judges, demo video, and marketplace listing.** This is the one capability no
competitor submission has: MamaGuard remembers the patient across visits, and the
memory lives *inside FHIR itself*.

## The 90-second pitch

> "AuthPilot is stateless. Clinical Oracle is stateless. Every other agent in this
> hackathon treats each patient interaction as the first one. MamaGuard doesn't.
>
> Last month Dr. Kim saw Maria and declined a metformin titration because Maria
> reported severe GI intolerance. That decision is now persisted as a FHIR
> `DocumentReference` on the same server that holds every other resource about
> Maria — same access controls, same audit trail, same HIPAA boundary.
>
> When Maria comes in today and a new MamaGuard session opens from scratch, the
> agent's first move is to query `DocumentReference?subject=Patient/maria-001&
> category=clinical-reasoning-history&_sort=-date&_count=5`. Dr. Kim's note lands
> in the system prompt before the model even sees today's message.
>
> Result: MamaGuard does not re-recommend metformin. It cites Dr. Kim's prior
> decision by date. It carries forward the housing referral status. It defaults
> to the French interpreter without asking.
>
> Zero new infrastructure. Any other agent on the Prompt Opinion marketplace can
> read MamaGuard's memory with a standard FHIR query. This is what A2A + COIN look
> like when you stop treating them as RPC and start treating them as shared state."

## Live demo script

**Setup (once, before recording):**

```bash
cd medical-hackathon-v3
docker ps | grep hapi                    # verify HAPI up on :8090
uv run python scripts/load_bundles.py    # ensure Maria exists
uv run python scripts/demo_memory_recall.py --seed-only
```

**Recording flow:**

1. **Show Maria has no memory yet** — call the agent against Maria, show that
   neither the response nor the FHIR server has any prior-visit memory.
2. **Seed visit 1** — run `scripts/demo_memory_recall.py --seed-only` and show
   the `DocumentReference` landing on HAPI (open `http://localhost:8090/fhir/
   DocumentReference?subject=Patient/bench-maria-001&category=clinical-reasoning-history`).
3. **Visit 2, fresh session** — open a brand-new A2A session against the same
   patient. In the agent's `<patient-memory>` block (visible if you enable verbose
   logging), point out Dr. Kim's note has been lifted in.
4. **Show the behaviour change** — the agent's Talk section references Dr. Kim
   explicitly, the Task section omits metformin, the SDOH section treats the
   housing referral as in-flight rather than new.
5. **Cross-agent interop** — open a new Prompt Opinion agent (not MamaGuard) and
   issue the same `DocumentReference` query. Show that any agent on the
   marketplace can read the memory; this is what interoperability at the
   standard level buys you.

## Why this answers the judging criteria

| Criterion | How memory recall answers it |
|---|---|
| **AI Factor** | GenAI alone can't manufacture continuity — rule engines definitely can't. This is a concrete capability that scales beyond demo into longitudinal care. |
| **Potential Impact** | Forgetting prior decisions is a documented cause of medication errors, duplicate referrals, and avoidable re-screening. Maternal care specifically turns on 10–12 visits in 9 months — continuity is the product. |
| **Feasibility** | Memory stored as FHIR `DocumentReference` inherits the server's HIPAA boundary and audit trail. No sidecar DB, no new access-control surface, no separate compliance story. |

## Schema

See `docs/session_brain_dump_2026_04_16.md` for the authoritative schema. Short version:

```json
{
  "resourceType": "DocumentReference",
  "subject": {"reference": "Patient/{id}"},
  "category": [{"coding": [{
    "system": "http://mamaguard.ai/codes",
    "code": "clinical-reasoning-history"
  }]}],
  "type": {"coding": [
    {"system": "http://mamaguard.ai/codes", "code": "agent-memory-note"},
    {"system": "http://mamaguard.ai/codes", "code": "trajectory"}
  ]},
  "author": [{"display": "MamaGuard v3"}],
  "content": [{"attachment": {"contentType": "text/markdown", "data": "<base64>"}}]
}
```

Memory subtypes (on `type.coding[1]`): `trajectory`, `trajectory-elevated`,
`feedback` (clinician overrides), `plan` (in-flight care plans).

## Talking points the demo video must land

- "Memory lives in FHIR, not in MamaGuard."
- "Dr. Kim's decision is durable — it outlasts any container restart, and it's
  readable by any other agent on the marketplace."
- "Zero new infrastructure — one additional resource type on a server that was
  already there."
- "This is what A2A + COIN look like when you implement them at the data layer,
  not just as RPC."

## Files

- `scripts/demo_memory_recall.py` — seed / preview / cleanup
- `mamaguard/shared/memory.py` — `inject_memory_block` + `persist_memory_note`
- `mamaguard/tests/test_memory.py` — unit tests
- `docs/session_brain_dump_2026_04_16.md` — Phase 4 decision log
