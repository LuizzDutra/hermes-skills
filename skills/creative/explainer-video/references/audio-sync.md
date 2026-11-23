# Audio sync for narrated video

Everything here exists because beats placed by word-count estimates drift catastrophically: a scene whose
narration runs 140 s can be 40 s out by the second beat if the paragraphs are dense early and sparse late.

## 1. Turn the script into a timing guide (TTS)

`edge-tts` is the cheapest workable guide voice. It is usually **not** in the agent's own venv and that venv may
have no pip; make a dedicated one:

```bash
uv venv .tts --python 3.11
uv pip install --python .tts/Scripts/python.exe edge-tts
```

Brazilian Portuguese voices available: `pt-BR-AntonioNeural` (male), `pt-BR-FranciscaNeural` (female),
`pt-BR-ThalitaMultilingualNeural` (female). Assign one voice per narrator so each person recognises their block.
Confirm the list with `edge-tts --list-voices` before a batch: an invented voice name fails only for the scene
that used it, and a batch that swallows the error ships a silent block.

These voices emit **`SentenceBoundary`**, not `WordBoundary` — ask for both types and keep whichever arrives:

```python
import asyncio, edge_tts

async def grab(txt, voice, path):
    marks, audio = [], bytearray()
    async for ch in edge_tts.Communicate(txt, voice, rate="+0%").stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] in ("SentenceBoundary", "WordBoundary"):
            marks.append((ch["offset"] / 1e7, ch.get("duration", 0) / 1e7, ch["text"]))
    open(path, "wb").write(audio)
    return marks
```

`offset` and `duration` are in 100-nanosecond units: divide by 1e7 for seconds.

**Verify before trusting the marks.** Re-generate the same text/voice/rate and compare the new duration with the
file already in the cut; a delta under ~0.1 s means the timings describe that exact audio.

## 2. Pronounce acronyms without corrupting words

TTS reads `CSRD` as a word and `UE` as "ue". Fix it with **word-boundary** substitution, never `str.replace`:

```python
SUB = [("CSRD", "C S R D"), ("CVM", "C V M"), ("UE", "União Europeia"), ("kW", "quilowatts")]
txt = re.sub(rf"(?<![A-Za-zÀ-ÿ]){re.escape(k)}(?![A-Za-zÀ-ÿ])", v, txt)
```

Naive replacement turns `QUE` into `QUnião Europeia` and `ATIVIDADE` into `AT IVIDADE`, and the synthesiser can
return "No audio received" because the text no longer parses. Spelling acronyms also makes the block longer —
budget 1–3 s per acronym when validating slot lengths.

## 3. Cue map: the artefact that makes re-timing cheap

Keep one JSON: `scene -> [{t, dur, text}, ...]` plus `timeline.json` with each scene's absolute start/end. Every
beat in every scene module is then defined as "starts when sentence N starts", not "starts at 34.0 s".
The same map writes the `.srt` (one cue per sentence span) and drives the re-timing brief in §7.

## 4. Diagnose drift

Build a table per scene: beat, the sentence it illustrates, the measured instant, the beat's current instant.
Report two numbers — **first deviation** and **worst deviation**. Anything above ~2 s is a defect; 10 s+ means
the beat map is wrong, not that the animation is slow.

Symptom to recognise: the video leaves a number on screen while the audio is still describing the previous
metric. That is a beat boundary placed by feel.

## 5. Re-timing rules

- **Move windows, do not rescale globally.** A uniform time-warp works only when every ratio is near 1, and even
  then it aligns only the beat boundaries: the reveals inside a beat keep their design lead, so the counter closes
  seconds after the word was spoken. Once one sentence runs 20 s (a dense legal paragraph) and the next runs 2 s,
  a warp squeezes the tail to 0.4× and the reveals become unreadable. Warp to rescue a draft; re-time for delivery.
- **Reorder first when the narration order differs.** A warp is monotonic and cannot fix out-of-order beats — if
  the script says "the question is this" before "it asks three things", the scene must show the question first.
- **Compressed beat → cut content, not speed.** Drop a sub-element, merge two reveals, shorten the copy.
- **The last beat must end with the last spoken sentence.** No 10 s tail of credits over silence, no content cut
  off at the boundary.
- **Re-render and re-check by sampling frames at each new beat start**, comparing the on-screen subject with the
  sentence text at that instant. A contact sheet with the sentence printed under each frame makes the check one
  glance per scene. Sample the **assembled master** at absolute time (scene start + cue), not the scene mp4 — the
  offsets that break sync live in the assembly, and checking the clip validates a file nobody watches.

## 6. Budgeting the script itself

Words ÷ 145 = minutes of speech at a calm delivery. Compare with the slot: above ~170 wpm the narration has to
be rushed and text should be cut; below ~100 wpm the scene is mostly silence and needs B-roll or deliberate
pauses. Acronyms spelled out inflate the spoken length and belong in the same budget.

## 7. The re-timing brief

Hand whoever wrote the scene a table, not a diagnosis: each beat, the sentence it illustrates, that sentence's
measured start, and the window the new timing gives it. Then state the constraints:

- **Do not redesign.** Only windows move; coordinates, copy and colour stay.
- **Work in local time.** Convert each beat to `lt = t - start` so its internals survive the window moving.
- **Short window → less content**, not faster animation.
- **Beats with no sentence are deleted**, and the deletion is reported as a script change.
- **Return a table**: beat → start → end → sentence heard at that instant, plus every deliberate deviation from
  the map and why.

Expect two kinds of pushback and take both seriously: the author who says a beat cannot fit its new window, and
the author who says the map slices a sentence in half because that line is the previous beat's payoff. Both are
usually right — the map is a plan, not a verdict.

One more consequence worth warning about: an element can end up **earlier than the sentence that names it**. When
that happens the element moves to the beat the audio is currently on (a projection figure migrating to the panel
being discussed) instead of sitting on screen 20 s in advance.

## 8. The real recordings arrive

The guide voice did its job; now the four narrators send one file per scene. Do not hand-align: use speech
recognition as a **clock**, never as a transcriber — you already know the text, you only need the instants.

1. **Probe the files.** `ffprobe` for duration/channels, `volumedetect` for peaks. Expect mixed mono/stereo and a
   wide level spread (a 6 dB gap between narrators is normal); no clipping does not mean matched levels.
2. **Word timings with faster-whisper** (CPU is fine, ~40 s per minute of audio at `small` / `int8`):

   ```bash
   uv pip install --python .tts/Scripts/python.exe faster-whisper
   ```

   ```python
   from faster_whisper import WhisperModel
   m = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=6)
   segs, info = m.transcribe(path, language="pt", word_timestamps=True,
                             vad_filter=True, beam_size=1,
                             condition_on_previous_text=False)
   ```

   The transcript will be wrong in places ("7,6 milhões de **euros**" for "litros"). Ignore it: only `word.start`
   and `word.end` matter, and a misheard word still occupies its real time span.
3. **Align script → words, not index → index.** Normalise both sides (lowercase, strip punctuation), run
   `difflib.SequenceMatcher` over the token lists, map each script token to its matched word index, and take a
   sentence's start as the minimum start among its matched words. Two maps built from the same script do not
   necessarily have the same sentence count — the TTS emitter merges short sentences, the script does not — so a
   positional `zip` silently shifts every pairing.
4. **Cobertura como QA.** Report matched/total per scene; 80–95% is normal and the misses are usually two-word
   lines ("Olá.", "Tudo.") that the recogniser folded into the next sentence. A *whole* sentence with no match is
   a real deviation — the narrator improvised or cut it — and the on-screen copy then follows the recording, not
   the script (a closer that says "no nosso quiz" must not stay "atividade do módulo" on screen). The exception is
   proper nouns and technical names: keep the correct written form even when the voice slips — the course stays
   "Sistemas de Informação", plural, whatever the narrator said.
5. **Re-dispatch the re-timing brief (§7) with the new durations.** Do not try to salvage the old timing: the
   recordings run ±10 s per scene, and a warp only moves the boundaries inward.
6. **Build the narration master with delays, not concat.** Per block: mono, 48 kHz, `loudnorm=I=-23:TP=-2:LRA=9`
   so the four voices match; then place each block on an `anullsrc` bed of the film length with `adelay`, and mix
   with `amix=inputs=N:normalize=0`. Concat would discard the inter-scene gaps, which are part of the edit.
7. **Re-export the subtitles from the new cue map.** The old `.srt` inherited the guide's drift and is now wrong
   by exactly the amount the takes differ.
8. **Re-budget the gaps.** Gaps were sized to swallow the guide's pauses; with tighter real takes they become dead
   air — a 14 s montage built to hide a TTS pause ends up between two sentences that barely breathe. Shrink the
   long ones to a deliberate montage length (6–8 s), leave the rest at the 1.2 s breath, and re-cut the B-roll to
   the new spans: footage chosen for the old gap lengths needs re-trimming, not re-shooting.
