# Demo GenAI Prompts — Maria B-roll

Prompts for generating the demo-patient imagery and motion clips used in the 3-minute submission video. Paste verbatim into the listed tools.

**Disclaimer required in video + Devpost:** *"Patient imagery is AI-generated. All FHIR data is synthetic."*

## Tool recommendations (April 2026)

| Purpose | Tool | Notes |
|---|---|---|
| Stills | Google Imagen 4 / Nano Banana (via Gemini) | Strongest skin-tone realism, free |
| Stills | Midjourney v6/v7 `--style raw` | Best documentary feel, $10/mo |
| Stills | Flux.1 [pro] (fal.ai / Replicate) | ~$0.05/img, excellent photoreal |
| Img2video | Runway Gen-4 | Editorial tone, motion control, $15/mo |
| Img2video | Luma Ray 2 | Fast, ~$0.40/clip |
| Img2video | Kling 2.0 Master | Best realistic micro-motion, ~$1/clip |
| Text2video | Google Veo 3 | Realism + ambient audio |

Avoid DALL-E 3 (over-smooths Black skin) and Sora without API access.

## Workflow

1. Generate 4 stills (prompts §1).
2. Pick the best hero take. For Shots 2 and 3, img2img-seed from the hero to lock face continuity.
3. Feed each still into an img2video tool with the matching motion prompt (§2).
4. Generate 4 takes per clip. Reject any with face morph, googly eyes, or over-dramatic motion.

---

## §1 — Still image prompts

### Shot 1 — Hero portrait

```
Documentary portrait of a Black woman in her late 30s, Haitian features, warm
brown skin, greying at temples, short natural coils or simple scarf, fine lines
around tired eyes, looking off-camera with quiet weariness — not sad, dignified
and contemplative. Soft natural window light from the left, shallow depth of
field, muted clinical interior background, slight motion blur in background.
Shot on 85mm, f/1.8, photojournalism style, 35mm film grain, desaturated warm
palette. No smile, no teeth, no glamour lighting. Medium close-up, head and
shoulders. --ar 3:2 --style raw --v 6
```

### Shot 2 — Postpartum with Lucas

```
Intimate documentary photograph of a Black woman in her late 30s cradling a
sleeping newborn to her chest in a hospital recovery room. She wears a simple
gray hospital gown, IV visible on her forearm, looking down at the baby with
exhausted tenderness. Soft window light, faded blue hospital blanket, slight
clinical clutter in background (blurred monitor). 50mm lens, natural grain,
muted palette, National Geographic style, no posed smile. --ar 4:5 --style raw --v 6
```

### Shot 3 — Clinical encounter

```
Over-the-shoulder documentary photograph: a Black female nurse-practitioner
in scrubs gently taking the blood pressure of a seated Black woman patient in
her late 30s, Haitian features. Patient is the focus, face visible, eyes lowered
and thoughtful.
Clinic exam room, soft overhead fluorescent softened by a window. Shot from
mid-distance on a 35mm lens, candid, no eye-contact with camera. Photojournalism,
muted institutional colors, film grain. --ar 16:9 --style raw --v 6
```

### Shot 4 — Data-stakes visualization

```
Conceptual editorial photograph: a Black woman in her late 30s from behind,
sitting in a clinic waiting room, surrounded by translucent layered paper
medical charts floating in the air around her, BP readings and lab numbers
visible but out of focus. Dim window light, cinematic, muted blue-grey palette,
shallow depth of field, sense of overwhelm. --ar 16:9 --style raw --v 6
```

### Universal negative prompt (if supported)

```
cartoon, illustration, 3d render, cgi, plastic skin, beauty filter, glamour
lighting, heavy makeup, studio backdrop, forced smile, teeth, watermark, text,
extra fingers, distorted hands, warped face
```

---

## §2 — Img2video motion prompts

Each prompt assumes you upload the matching still. Target 5–6 seconds, 24fps.

### Shot 1 — Hero animated (5s)

```
Static locked camera, documentary portrait. The woman breathes slowly and
naturally — chest rises once, then falls. Eyes stay fixed off-camera in
quiet thought, then a single slow, heavy blink around second 3. Barely
perceptible head tilt two degrees toward the light. Loose strand of hair
shifts with her breath. No camera movement, no zoom, no pan, no parallax.
Natural window light from screen left, soft and unchanging. Warm desaturated
palette, 35mm film grain, 24fps. 5 seconds. Photojournalism, not cinema.
```

### Shot 2 — Postpartum animated (6s)

```
Mother gently breathing, newborn chest rising. Her eyes slowly close as she
rests her cheek on baby's head. Static camera, no zoom. Warm natural light,
slow and tender pace.
```

### Shot 3 — Clinical encounter animated (5s)

```
Nurse wraps BP cuff around patient's upper arm in a single smooth motion.
Patient's eyes lower to watch. Static handheld camera with very slight natural
sway. Documentary tone, no dramatic music cues.
```

### Shot 4 — Data stakes animated (4s)

```
Translucent paper charts drift slowly around the seated woman, as if floating
in water. She remains still, contemplative. Cinematic, slow-motion, blue-grey
ambient. Static camera.
```

### Video negative prompt

```
smile, teeth, laughing, dramatic turn, camera movement, zoom, dolly, pan,
warp, morphing face, extra fingers, glamour lighting, cinematic color grade,
beauty filter, flashing eyes, artificial tears
```

### Tool-specific tweaks

- **Runway Gen-4** — Motion = 2/10. Higher values break face.
- **Luma Ray 2** — "Keyframes" mode with start frame only; no end frame.
- **Kling 2.0** — "Professional Mode" + Creativity 0.3.
- **Veo 3** — append `audio: subtle room tone, distant fluorescent hum, no music`.

---

## §3 — 3-minute shot sheet

| Time | Shot | Source |
|---|---|---|
| 0:00–0:08 | Hero Maria animated + stat overlay "CDC: 700 US women die yearly. 3× more if Black." | AI video (Shot 1) |
| 0:08–0:25 | Data-stakes shot + voiceover of problem | AI video (Shot 4) |
| 0:25–2:15 | Platform demo — PO, agent collab, FHIR writeback, handoff to Lucas | Screen recording |
| 2:15–2:40 | Benchmark cards (93.1% / +30% / 0 fabrications / SMART Permission Tickets) | Static graphics |
| 2:40–2:55 | Postpartum shot animated + voiceover close | AI video (Shot 2) |
| 2:55–3:00 | Logo + "Published on Prompt Opinion Marketplace" + URL | Static |

Burn in captions (CapCut auto-caption or ElevenLabs transcription). Judges often watch muted.
