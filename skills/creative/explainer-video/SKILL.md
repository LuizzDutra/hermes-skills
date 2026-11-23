---
name: explainer-video
description: "Explainer videos: Pillow motion graphics + ffmpeg."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Video, Motion-Graphics, Pillow, FFmpeg, TTS]
    related_skills: [manim-video, ascii-video]
---

# Explainer video: script → narrated motion graphics

## When to use

Any scripted video deliverable — course module, videoaula, product explainer, training piece, documentary-style
short — where the visuals are typography, data and diagrams instead of footage. Also when someone hands you a
roteiro and asks to "montar o vídeo".

Not for math/equation animation (use `manim-video`) or character-art video (use `ascii-video`).

A text-heavy documentary explainer is **not** Manim work either, and it is worth saying so before someone proposes
it: there are no equations to typeset, the copy is long-form prose in a natural language, and Manim's Pango
renderer pushes proportional fonts toward broken kerning, which ends in monospace type that reads like a code
lecture. The Pillow core in this skill exists for this shape — one renderer, real fonts, full typographic control.

## Standing rules (apply to every instance)

- **Timing comes from the real audio, never from an estimate.** Placing beats by word count drifts 10–40 s inside a
  single 2-minute scene. Only measured timings are safe — see `references/audio-sync.md`.
- **No scene numbers on screen.** The viewer does not need "Cena 4"; put a constant brand line top-left instead.
- **Every shot moves.** A still frame longer than ~1 s reads as a slide, and course rubrics frequently forbid slide
  format in so many words.
- **Never invent numbers.** Every figure comes from the script or its data sheet and carries a source line while
  it is on screen.
- **On-screen copy follows the spoken take, except proper nouns.** When a narrator improvises ("no decorrer do
  minicurso" for "nos próximos treze minutos") the card updates to match the voice — copy that contradicts what is
  being said is a defect. Programme, course and technical names are the exception: keep the correct written form
  even when the voice slips, because a wrong name on screen outlives the audio.
- **B-roll is a marked gap, not black.** Render a slate with the shot description and its exact time span, so the
  editor drops footage in without re-timing anything.
- **Hand off the clean master; captions travel as a sidecar.** The review copy ships without burned captions,
  with the `.srt` beside it and the absolute path of the master in the message: re-burning is one command, and the
  person reviewing needs to see the design, not a subtitle box. Burn only for the version that is actually
  submitted, and delete superseded exports from the delivery folder — two MP4s that differ by one filter is how
  the wrong file gets sent.
- A scene that could be swapped for a slide without loss is not finished.

## Pipeline

1. **Parse the script into blocks with durations.** Extract the `.docx` with the stdlib (`zipfile` +
   `ElementTree` over `word/document.xml`); a paragraph is the unit. Close a narration block on **any** paragraph
   that starts with `[` — matching only `…]` lets stage directions such as `[TEXTO NA TELA] …` merge into the
   narration and inflates the count by a third, enough to condemn a scene that is actually fine. Count narration
   words per block; at ~145 wpm the word count divided by 145 is minutes of speech. A slot with more than ~15%
   silence needs trimming, or the silence is intentional breathing and must be designed for.
2. **Generate the timing guide.** TTS the narration block by block, one file per scene; measure with ffprobe and
   write `timeline.json` (start, end, duration per scene). Recipe in `references/audio-sync.md`.
3. **Build a shared visual core** — palette, fonts, easing, text fitting, frame class, ffmpeg pipe. This is what
   makes eight separately-authored scenes look like one film, and what lets you parallelize them. Copy
   `templates/core.py`.
4. **One module per scene**: `gfx/scNN.py`, importing the core, rendering `gfx/out/scNN.mp4` at the exact scene
   duration.
5. **Parallelize scenes with subagents** — one task per scene. Each brief carries the core contract, its beat
   table with timecodes, its exact duration, the standing rules above, and the requirement to preview frames and
   verify margins before the final render. Dispatch from an explicit scene list and, when the batch returns, diff
   `gfx/out/` against that list: a scene nobody commissioned produces no error, only a hole in the film that shows
   up when a human watches it.
6. **QA each clip**: ffprobe duration within 0.2 s of target, 1920×1080, 30 fps, h264; then contact sheets
   (3 frames per scene) inspected visually for collisions and margin overflow.
7. **Assemble**: concat scene clips, fill the inter-scene gaps with slate cards, mux narration, normalise
   loudness. Commands in `references/ffmpeg-assembly.md`.
8. **Subtitles**: build the SRT from the cue map, one cue per sentence span, split only when the sentence is too
   long for two lines. A subtitle timed by character share inherits exactly the drift the beats had — proportional
   timing is acceptable only before any guide audio exists.
9. **When the real recordings arrive, replace the clock — not the film.** Transcribe only to obtain word timings,
   align that transcript to the known script, rebuild the cue map from the recording's real sentence starts, and
   re-run the per-scene re-timing brief. Scene durations will move by ±10 s, so the film total is recomputed, not
   adjusted. Recipe in `references/audio-sync.md` §8.

## Diagnosing sync

Never accept "looks roughly synced". Build a cue table — for each beat, the sentence it illustrates and the
measured instant that sentence starts — and report drift per scene as *first deviation* and *worst deviation*.
A beat starting more than ~2 s off is a defect. Method and numbers in `references/audio-sync.md`.

## Pitfalls

- **Placeholder cards rendered with ffmpeg `drawtext` break on Windows.** The colon in `C:/Windows/Fonts/...` and
  commas or em dashes in the text are filter metacharacters, so the graph parses wrong and ffmpeg aborts with
  "No option name near". Render cards in Pillow instead — same visual system, no escaping.
- **PIL `ImageDraw` on an RGBA overlay does not composite shape-over-shape.** A translucent rect drawn over
  another shape writes its alpha and punches a hole. Pre-mix the colour against the known background and draw
  opaque, or composite in a separate layer.
- **Concatenating with `-f concat -safe 0` can silently drop a clip.** With mixed timebases it produced a master
  61 s short while exiting 0 — the hole only shows when someone watches. Build the concat as a filter graph with
  every part as its own input (`concat=n=N:v=1:a=0`) and assert the output duration against the sum of the parts.
- **B-roll gaps must be computed, not remembered.** Derive each gap as `next_scene_start − previous_scene_end`
  from `timeline.json`, pad the source to that exact length (`tpad=stop_mode=clone:stop_duration=1`, then `-t`),
  and assert the total. A clip 30 ms short shifts every beat after it.
- **Test the burned credit over the brightest frame, not on black.** A credit that reads fine on a dark scene
  disappears over crushed stone or sky; draw a semi-transparent scrim behind the text and inspect the credit on
  the lightest footage of the batch before assembling.
- **An overlay that starts at 0.05 s leaves the first frames on the placeholder.** Frame 0 is what a player shows
  while it buffers and what a thumbnail grabs; `enable='between(t,0.05,…)'` renders two frames of the empty card
  and comes back as "the footage doesn't appear at the start". Start composited footage at `t=0` and inspect frame
  0 of the assembled file — checking frame 30 proves nothing about the opening.
- **Draw order beats intention.** A panel, card or slate drawn after a counter erases the counter. Background
  panels first, content after; never let a decorative box be the last thing in the frame.
- **A clip rendered before its module's last edit is stale.** Subagents (and you) edit `scNN.py` after rendering,
  so compare mtimes with `gfx/out/scNN.mp4` before assembling: a scene whose source is newer than its render ships
  the previous timing and still passes every duration check. Re-render, then re-verify.
- **Only one element may own the bottom strip.** A per-shot source line and a global credit at the same y become
  unreadable.
- **Squeezing is not retiming.** When a beat's new window is far shorter than its design, cut elements instead of
  accelerating the animation 4× — frantic reveals read as defects.
- **Every beat must own a sentence.** After building the cue map, delete any beat that has no narration behind it;
  recap cards, closers and "verifiable proof" bows are the usual orphans. Deleting them is a script change — name
  what went when you report, never bury it in a changelog.
- **A timing guide is not the final narration.** Keep the beat↔cue map in JSON so swapping in real voices costs
  one regeneration, not a redesign.
- **Two cue maps of the same script can have different sentence counts.** The TTS boundary emitter merges a short
  sentence ("2024.") into the next one, so the guide map carries 11 marks where the script has 12; zipping the two
  by index shifts every pairing by one and the resulting warp looks plausible while mapping the wrong sentences.
  Pair by token overlap (`difflib`), never by position — and print the pairs before rendering anything.
- **A global time warp fixes beat starts and nothing else.** Even when every old/new ratio is near 1, a counter
  keeps its design lead, so it still closes 3 s after the number is spoken. Use a warp only to rescue a rough cut;
  for delivery, re-time each scene so the reveals land on the words.
- **A full-length cut is too large to attach in chat.** Export a ~60 s, 720p, CRF 25 sample (under ~1 MB) and give
  the absolute path of the master.

## References

- `references/audio-sync.md` — TTS timing extraction, cue maps, drift diagnosis, re-timing procedure, re-timing brief.
- `references/pillow-renderer.md` — frame class, typography, easing, safe margins, performance.
- `references/ffmpeg-assembly.md` — concat, gap slates, loudness targets, subtitle burn, delivery sizes.
- `templates/core.py` — shared visual library to copy per project.
- `scripts/sync_check.py` — prints every sentence of a scene over the frame that plays when it is spoken; run it on the assembled master, one sheet per scene.
- `scripts/align_asr.py` — cue map for real recordings: faster-whisper word timings aligned to the script by token overlap, plus a per-sentence coverage report that flags improvised or cut lines.
