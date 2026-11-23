# Assembly, loudness and subtitles

## Concat

Scene clips rendered with identical parameters (1920×1080, 30 fps, h264, yuv420p) concatenate safely. When in
doubt, re-encode once through the concat demuxer rather than trusting stream-copy:

```bash
ffmpeg -y -f concat -safe 0 -i concat.txt -i narration.wav \
  -filter_complex "[0:v]setpts=PTS-STARTPTS[v];[1:a]aformat=sample_rates=48000:channel_layouts=mono,\
loudnorm=I=-16:TP=-1.5:LRA=11[aout]" \
  -map "[v]" -map "[aout]" -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p \
  -c:a aac -b:a 160k -ar 48000 -movflags +faststart -shortest out.mp4
```

Concat only the *clips*: the narration is a single mixed track laid under the whole film, not per-scene audio.

## Fan-out: one label, one consumer

A filtergraph label feeds exactly one input. Routing the voice into both the ducking sidechain and the final mix
fails with `Error binding filtergraph inputs/outputs: Invalid argument` — and the message names neither the label
nor the filter, so it reads like a syntax error. Split first:

```
[16:a]aformat=sample_rates=48000:channel_layouts=mono,loudnorm=I=-16:TP=-1.5:LRA=11[voz];
[voz]asplit=2[vsc][vmix];
[mus][vsc]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[duck];
[duck][vmix]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[aout]
```

Same rule for any stream consumed twice (a video used as both overlay and mask).

## Music bed

A two-minute royalty-free track under a thirteen-minute film has to loop, and the loop point is where the seam
lands, so put the fades at the film's edges, not at the join.

```bash
ffmpeg -y -i film.mp4 -stream_loop -1 -i track.wav \
  -filter_complex "[0:a]anull[voz];\
[1:a]aformat=sample_rates=48000:channel_layouts=mono,volume=0.28,apad,atrim=0:758.4,\
afade=t=in:st=0:d=2.5,afade=t=out:st=753.4:d=5[mus]" ...
```

- `-stream_loop -1` on the input plus `atrim` to the film length. Without the trim the graph never ends and
  `-shortest` truncates the picture to the music instead of the music to the picture.
- Match channel layouts before `amix`; folding the music to the voice's mono is simpler than carrying stereo
  through the graph.
- Level the bed by measurement, not by ear. With the voice normalised to −16 LUFS, a music mean around **−33 dB in
  the speech gaps** against **−17 dB on speech** gives ~15 dB of separation. A −17 dB track at `volume=0.28` lands
  close; verify with `volumedetect` on a three-second silence and on a three-second speech stretch.
- Duck with `sidechaincompress`, then `loudnorm` the **mixed** output — summing raises integrated loudness.
- Re-render the credits clip when a placeholder track becomes a real one: a `[faixa royalty-free]` line left in the
  roll is a missing attribution, not a detail.

## Footage inside a designed card

When a scene reserves a rectangle for B-roll (`slate()` in the shared core), composite the clip into that box
instead of re-rendering the scene:

- scale to **cover** and crop centre — `scale=W:H:force_original_aspect_ratio=increase,crop=W:H,setsar=1`.
- inset the overlay by ~4 px so the card's own stroke survives, and re-stroke with `drawbox` if the footage covers
  it; the border is what keeps the shot reading as a window rather than a rectangle pasted on black.
- `enable='between(t,0,END)'`. Starting at 0.05 s leaves the first one or two frames on the placeholder.
- Burn the shot credit inside the card (Pillow, scrim behind the text), not across the full frame.

## Sourcing the stock clips

A downloaded clip rarely opens on the shot that reads: a 28 s quarry clip began on a tight close-up of crushed
stone, and the wide establishing shot was at 20 s. Sample before choosing the in-point.

```bash
for t in 0 4 8 12 16 20; do ffmpeg -y -ss $t -i clip.mp4 -frames:v 1 q$t.png; done
```

Lay the stills out as one contact sheet and pick `trim=start=` from what you see. Then check headroom against the
gap it must fill: 20 s into a 28 s clip leaves 8 s, so a 16 s gap cannot start there — split the plan (wide shot
first from another in-point, detail second) or shorten the gap. Do not stretch 8 s of footage across 16 s of
silence to hit a duration.

## Gap slates

Gaps between scenes exist because narration pauses. Fill each with a card rendered by the same Pillow core —
label, requested shot and the exact span (`1:01,0 – 1:15,0 · 14,0 s`) — so the editor knows what to drop where.
Never use ffmpeg `drawtext` for this: Windows paths and commas inside the text break the filter graph.

## Loudness

Target −16 LUFS integrated, true peak −1.5 dBTP for web/course delivery (−14 LUFS if the destination is
YouTube). Verify what actually landed instead of trusting the filter:

```bash
ffmpeg -i out.mp4 -af loudnorm=print_format=summary -f null -
```

`Input Integrated / Input True Peak` are the values of the file; that is the pair to report.

## Subtitles

Time the SRT from the cue map of whatever audio is in the cut — the TTS guide first, the real recordings later
(`references/audio-sync.md` §3 and §8). Cap the cue at ~88 characters across two lines of ~44 and enforce a
~1.1 s minimum. Proportional character-share timing is a fallback for a cut with no audio yet; the moment
narration exists the cue map is exact and costs nothing extra.

Burn for the delivered version:

```bash
ffmpeg -y -i in.mp4 -vf "subtitles=subs/x.srt:force_style='FontName=Arial,FontSize=26,PrimaryColour=&H00F5F2EE,\
Outline=1,Shadow=1,MarginV=124,BackColour=&HA0000000,BorderStyle=4,Outline=0,Shadow=0'" -c:v libx264 -crf 19 -preset fast -pix_fmt yuv420p -c:a copy -movflags +faststart out_leg.mp4
```

Keep two lines maximum and a semi-transparent box — the accessible choice for a course deliverable. Run ffmpeg
from the project root so the filter takes a relative path: on Windows the drive-letter colon is a filter separator
and the graph dies exactly like `drawtext` does.

**MarginV must clear the per-shot source line.** The visual system parks `FONTE …` around y = H−92, so a MarginV
of 40–50 lands the subtitle on top of the credit. At 1080p, 120–130 holds two 26 px lines above it. Sample a frame
that carries both a source line and a subtitle and inspect the bottom band before exporting — the overlap is
invisible in a thumbnail and obvious on playback.

## Delivery

A 13-minute 1080p CRF 18 file lands around 45 MB, which chat attachments will refuse. Export a sample for review
— six to eight 8-second excerpts, 1280×720, CRF 25 — and it comes out under 1 MB:

```bash
ffmpeg -y -i cut.mp4 -filter_complex "\
[0:v]trim=12:20,setpts=PTS-STARTPTS,scale=1280:720[a];\
[0:v]trim=80:88,setpts=PTS-STARTPTS,scale=1280:720[b];\
[a][b]concat=n=2:v=1:a=0[v]" -map "[v]" -c:v libx264 -crf 25 -preset fast sample.mp4
```

Unconnected `atrim` labels abort the graph — build the filter chain with video only unless audio is needed.
