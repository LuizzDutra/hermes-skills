# -*- coding: utf-8 -*-
"""align_asr.py — cue map for REAL narration, using ASR only as a clock.

The script text is the source of truth; faster-whisper supplies the instants.
Output: <out>/frases_real.json in the same shape as the TTS cue map, so every
scene module and the SRT builder keep working unchanged.

    python align_asr.py --src gravacoes --roteiro roteiro.json --out audio/locucao

Requires faster-whisper in the python running it:
    uv venv .asr --python 3.11 && uv pip install --python .asr/Scripts/python.exe faster-whisper
"""
import argparse
import difflib
import json
import os
import re
import sys

PONT = re.compile(r"[^\wÀ-ÿ]+", re.UNICODE)


def tok(s):
    s = s.lower().replace("–", " ").replace("—", " ")
    return [t for t in PONT.sub(" ", s).split() if t]


def frases(txt):
    return [p for p in re.split(r"(?<=[.!?])\s+", txt.strip()) if p.strip()]


def transcreve(path, model, cache):
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=6)
    segs, _ = m.transcribe(path, language="pt", word_timestamps=True,
                           vad_filter=True, beam_size=1,
                           condition_on_previous_text=False)
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
             for s in segs for w in (s.words or [])]
    json.dump(words, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return words


def alinha(roteiro, words):
    """script sentence -> start time, by token overlap (never by index)"""
    fs = frases(roteiro)
    st, dono = [], []
    for i, f in enumerate(fs):
        for w in tok(f):
            st.append(w)
            dono.append(i)
    aw = [tok(w["w"])[0] if tok(w["w"]) else "" for w in words]
    sm = difflib.SequenceMatcher(None, st, aw, autojunk=False)
    ini, casados, total = {}, {}, len(st)
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            fi = dono[a + k]
            ini[fi] = min(ini.get(fi, 1e9), words[b + k]["s"])
            casados[fi] = casados.get(fi, 0) + 1
    marcas, ant = [], 0.0
    for i, f in enumerate(fs):
        t = ini.get(i, ant)
        nxt = next((ini[j] for j in range(i + 1, len(fs)) if j in ini), None)
        fim = min(nxt, words[-1]["e"]) if nxt else words[-1]["e"]
        fim = max(fim, t + 0.4)
        marcas.append({"t": round(t, 3), "dur": round(fim - t, 3), "txt": f,
                       "cobertura": round(casados.get(i, 0) / max(1, len(tok(f))), 2)})
        ant = fim
    return marcas, sum(casados.values()), total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="pasta com Cena1.wav … CenaN.wav")
    ap.add_argument("--roteiro", required=True, help="json {cena: texto}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small")
    a = ap.parse_args()

    rot = json.load(open(a.roteiro, encoding="utf-8"))
    res = {}
    for n in sorted(rot, key=int):
        src = os.path.join(a.src, f"Cena{n}.wav")
        if not os.path.exists(src):
            print(f"cena {n}: faltando {src}")
            continue
        w = transcreve(src, a.model, os.path.join(a.out, f"asr_c{int(n):02d}.json"))
        marcas, cas, tot = alinha(rot[str(n)], w)
        dur = round(w[-1]["e"], 2) if w else 0
        res[str(n)] = {"dur_mp3": dur, "marcas": marcas, "origem": "ASR+roteiro"}
        print(f"cena {n}: {dur:7.2f}s  {len(marcas):2d} frases  cobertura {100 * cas / max(1, tot):5.1f}%")
        fracas = [m for m in marcas if m["cobertura"] < 0.5]
        for m in fracas:
            print(f"   baixa cobertura ({m['cobertura']:.0%}) {m['t']:7.2f}s  {m['txt'][:70]}")

    p = os.path.join(a.out, "frases_real.json")
    json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ok", p, "| total de fala:", round(sum(v["dur_mp3"] for v in res.values()) / 60, 1), "min")


if __name__ == "__main__":
    sys.exit(main())
