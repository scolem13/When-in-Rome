#!/usr/bin/env python3
"""Convert the downloaded score corpora (~/Downloads/corpora, ~/Downloads/mutopia) to ABC, and catalogue everything.

    python3 Code/convert_scores_abc.py [stage ...]     stages: openscore dcml sapp local nottingham weimar billboard mutopia check catalogue
    Run with ~/Downloads/corpora/_tools/venv/bin/python (music21; python-ly) and lilypond on the PATH.
                                                        (none = all, in that order; finished files are skipped, so it resumes)

Where things go
  Scores/<Source>/...<name>.abc     sources whose licence allows sharing (CC0, CC BY-NC-SA, GPL, ODbL, CC0)
  Scores/Essen, Haydn-Quartets, Beethoven-Sonatas   CCARH data: personal research use only. In this PRIVATE repository;
                                     flagged "restricted" in the catalogue: never publish them or put them in teaching materials
  Scores/catalogue.csv               every piece from every source, with its ABC (if any), licence and abcjs check
  Scores/UNDONE.md                   what was not converted and why
Routes: MusicXML -> xml2abc (Wim Vree, ~/Downloads/corpora/_tools); MuseScore -> MuseScore 4 (-j batch) -> MusicXML -> xml2abc;
Humdrum -> music21 -> MusicXML -> xml2abc; Weimar Jazz DB -> music21 (quantised from bar/beat/tatum) -> xml2abc;
Billboard -> ABC chord charts written directly. Pieces already converted in Corpus/ (corpus_with_abc.csv) are not redone.
"""
import csv, json, os, re, sqlite3, subprocess, sys, tempfile, shutil, pathlib, fractions
from concurrent.futures import ProcessPoolExecutor

HOME = pathlib.Path.home()
WIR = pathlib.Path(__file__).resolve().parent.parent
OUT = WIR / "Scores"
CORP = HOME / "Downloads/corpora"
LOCAL = WIR / "Scores"   # the repository is private (2026-10-21), so the CCARH sets live here too, flagged in the catalogue
MUT = HOME / "Downloads/mutopia"
X2A = CORP / "_tools/xml2abc_177/xml2abc.py"
MSCORE = "/Applications/MuseScore 4.app/Contents/MacOS/mscore"
TMP = CORP / "_tmp"
LOG = OUT / "_convert-log.jsonl"
SITE = HOME / "Projects/everything-music-site"

LIC = {
    "OpenScore-Lieder": ("CC0 1.0", "github.com/OpenScore/Lieder"),
    "OpenScore-StringQuartets": ("CC0 1.0", "github.com/OpenScore/StringQuartets"),
    "DCML": ("CC BY-NC-SA 4.0", "github.com/DCMLab"),
    "Sapp-Mozart-Sonatas": ("CC BY-NC-SA 4.0", "github.com/craigsapp/mozart-piano-sonatas (Craig Stuart Sapp)"),
    "Sapp-Bach-Chorales": ("CC BY-NC-SA 4.0", "github.com/craigsapp/bach-370-chorales (Craig Stuart Sapp)"),
    "Nottingham": ("GPL-3.0", "github.com/jukedeck/nottingham-dataset"),
    "Weimar-Jazz": ("ODbL 1.0 / DbCL 1.0", "Weimar Jazz Database, Jazzomat Research Project, jazzomat.hfm-weimar.de"),
    "Billboard": ("CC0 1.0 (cite Burgoyne, Wild & Fujinaga, ISMIR 2011)", "McGill Billboard Project, ddmal.ca"),
    "Essen": ("CCARH licence: personal research use only", "github.com/ccarh/essen-folksong-collection"),
    "Haydn-Quartets": ("CCARH: rights to derivative editions reserved", "github.com/musedata/humdrum-haydn-quartets"),
    "Beethoven-Sonatas": ("CCARH: rights to derivative editions reserved", "github.com/craigsapp/beethoven-piano-sonatas"),
    "Mutopia": ("per piece (public domain or CC)", "mutopiaproject.org"),
}

def log(**k):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f: f.write(json.dumps(k, ensure_ascii=False) + "\n")

def x2a(xml, dest):
    """MusicXML (.mxl/.musicxml/.xml) -> dest .abc via xml2abc. Returns None or an error string."""
    dest = pathlib.Path(dest); dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP) as td:
        safe = pathlib.Path(td) / ("in" + pathlib.Path(xml).suffix)   # xml2abc reads [ ] in a path as a wildcard
        shutil.copy(xml, safe)
        r = subprocess.run([sys.executable, "-I", str(X2A), "-o", td, str(safe)], capture_output=True, text=True, timeout=600)
        safe.unlink()
        made = list(pathlib.Path(td).glob("*.abc"))
        if not made: return (r.stderr or r.stdout or "no output")[-300:]
        shutil.move(str(made[0]), dest)
    return None

def done(p): return pathlib.Path(p).exists() and pathlib.Path(p).stat().st_size > 0

# ── already in Corpus/ ────────────────────────────────────────────────────────
def corpus_index():
    have = {"paths": set(), "files": set()}
    f = WIR / "Corpus/corpus_with_abc.csv"
    if f.exists():
        for r in csv.DictReader(open(f)):
            if r.get("abc_file"):
                have["paths"].add(r["path"])
                if r.get("remote_score"): have["files"].add(r["remote_score"].rsplit("/", 1)[-1])
    return have

# ── OpenScore (MusicXML straight to xml2abc) ──────────────────────────────────
def _x2a_job(a): xml, dest = a; return (str(xml), str(dest), None if done(dest) else x2a(xml, dest))

def openscore():
    have = corpus_index(); jobs = []
    for name, repo in (("OpenScore-Lieder", "OpenScore_Lieder"), ("OpenScore-StringQuartets", "OpenScore_StringQuartets")):
        root = CORP / repo / "scores"
        for mxl in sorted(root.rglob("*.mxl")):
            rel = mxl.parent.relative_to(root)
            if name == "OpenScore-Lieder" and f"OpenScore-LiederCorpus/{rel}" in have["paths"]:
                log(stage="openscore", src=str(mxl), skip="in Corpus/"); continue
            jobs.append((mxl, OUT / name / rel / (mxl.stem + ".abc")))
        # quartet movements that only exist as MuseScore files
        if name == "OpenScore-StringQuartets":
            for ms in sorted(list(root.rglob("*.mscz")) + list(root.rglob("*.mscx"))):
                if not list(ms.parent.glob("*.mxl")): MS_JOBS.append((ms, OUT / name / ms.parent.relative_to(root) / (ms.stem + ".abc")))
    run_x2a(jobs, "openscore")

def run_x2a(jobs, stage):
    TMP.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for src, dest, err in ex.map(_x2a_job, jobs, chunksize=4):
            log(stage=stage, src=src, abc=dest, error=err)
    print(stage, len(jobs), "files")

# ── MuseScore (DCML, OpenScore quartet leftovers) ─────────────────────────────
MS_JOBS = []
def mscore_batch(jobs, stage):
    """[(mscx, dest.abc)] -> MusicXML through MuseScore's batch job, then xml2abc."""
    TMP.mkdir(parents=True, exist_ok=True)
    todo = [(s, d) for s, d in jobs if not done(d)]
    xmls = []
    for i in range(0, len(todo), 100):
        chunk, spec = todo[i:i + 100], []
        for s, d in chunk:
            x = TMP / "ms" / (re.sub(r"[^A-Za-z0-9]+", "_", str(pathlib.Path(d).relative_to(OUT))) + ".musicxml")
            x.parent.mkdir(parents=True, exist_ok=True)
            spec.append({"in": str(s), "out": str(x)}); xmls.append((x, d, s))
        jf = TMP / "ms-job.json"; jf.write_text(json.dumps(spec))
        subprocess.run([MSCORE, "-j", str(jf)], capture_output=True, timeout=3600)
        print(stage, "mscore", i + len(chunk), "/", len(todo), flush=True)
    for x, d, s in xmls:                      # a batch stops at a file it chokes on: retry the rest one at a time
        if not x.exists():
            try: subprocess.run([MSCORE, "-o", str(x), str(s)], capture_output=True, timeout=600)
            except subprocess.TimeoutExpired: pass
    ok = [(x, d) for x, d, s in xmls if x.exists()]
    for x, d, s in xmls:
        if not x.exists(): log(stage=stage, src=str(s), abc=str(d), error="MuseScore did not export")
    run_x2a(ok, stage)
    for x, d in ok: x.unlink(missing_ok=True)

def dcml():
    have = corpus_index(); jobs = []
    roots = [CORP / "DCMLab_ABC", CORP / "DCMLab_mozart_piano_sonatas"] + sorted(p for p in (CORP / "DCMLab_distant_listening_corpus").iterdir() if p.is_dir() and not p.name.startswith("."))
    seen = set()
    for root in roots:
        corpus = root.name.replace("DCMLab_", "")
        for ms in sorted(root.rglob("*.mscx")):
            key = (corpus if corpus != "ABC" else "ABC", ms.name)
            if ms.name in seen: continue
            seen.add(ms.name)
            if ms.name in have["files"]: log(stage="dcml", src=str(ms), skip="in Corpus/"); continue
            jobs.append((ms, OUT / "DCML" / corpus / (ms.stem + ".abc")))
    mscore_batch(jobs + MS_JOBS, "dcml")

# ── Humdrum through music21 ───────────────────────────────────────────────────
def _krn_job(a):
    krn, dest = a
    if done(dest): return (str(krn), str(dest), None)
    try:
        import music21, warnings; warnings.filterwarnings("ignore")
        s = music21.converter.parse(str(krn), format="humdrum")
        TMP.mkdir(parents=True, exist_ok=True)
        x = pathlib.Path(tempfile.mkstemp(suffix=".musicxml", dir=TMP)[1])
        s.write("musicxml", fp=str(x))
        err = x2a(x, dest); x.unlink(missing_ok=True)
        return (str(krn), str(dest), err)
    except Exception as e:
        return (str(krn), str(dest), f"{type(e).__name__}: {e}"[:300])

def run_krn(jobs, stage):
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for src, dest, err in ex.map(_krn_job, jobs, chunksize=4): log(stage=stage, src=src, abc=dest, error=err)
    print(stage, len(jobs), "files")

def sapp():
    jobs = [(k, OUT / "Sapp-Mozart-Sonatas" / (k.stem + ".abc")) for k in sorted((CORP / "craigsapp_mozart-piano-sonatas").rglob("*.krn"))]
    jobs += [(k, OUT / "Sapp-Bach-Chorales" / (k.stem + ".abc")) for k in sorted((CORP / "craigsapp_bach-370-chorales").rglob("*.krn"))]
    run_krn(jobs, "sapp")

def local():
    jobs = [(k, LOCAL / "Beethoven-Sonatas" / (k.stem + ".abc")) for k in sorted((CORP / "craigsapp_beethoven-piano-sonatas").rglob("*.krn"))]
    jobs += [(k, LOCAL / "Haydn-Quartets" / (k.stem + ".abc")) for k in sorted((CORP / "musedata_humdrum-haydn-quartets").rglob("*.krn"))]
    root = CORP / "ccarh_essen-folksong-collection"
    jobs += [(k, LOCAL / "Essen" / k.relative_to(root).with_suffix(".abc")) for k in sorted(root.rglob("*.krn"))]
    run_krn(jobs, "local")
    (LOCAL / "CCARH-RESTRICTED.md").write_text("Essen/, Haydn-Quartets/, Beethoven-Sonatas/: CCARH data converted for personal research only. Do not publish them or put them in teaching materials; keep this repository private while they are in it.\n"
                                     "Licences: ~/Downloads/corpora/ccarh_essen-folksong-collection/license.txt and the !!!YEC/!!!YEM lines in each .krn.\n")

# ── Nottingham: already ABC (several tunes a file) ───────────────────────────
def nottingham():
    root = CORP / "jukedeck_nottingham-dataset"
    for f in sorted(root.rglob("*.abc")):
        d = OUT / "Nottingham" / f.name; d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, d); log(stage="nottingham", src=str(f), abc=str(d), error=None)
    shutil.copyfile(root / "LICENSE.md", OUT / "Nottingham" / "LICENSE.md")

# ── Weimar Jazz Database: solos with their chords ─────────────────────────────
def weimar():
    import music21
    from music21 import stream, note, meter, key as m21key, harmony, expressions, tempo
    db = sqlite3.connect(CORP / "weimar-jazz/wjazzd.db")
    solos = db.execute("select melid, performer, title, titleaddon, instrument, style, avgtempo, rhythmfeel, key, signature from solo_info order by melid").fetchall()
    TMP.mkdir(parents=True, exist_ok=True)
    for melid, perf, title, addon, inst, style, bpm, feel, keyname, sig in solos:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", f"{perf}_{title}_{melid}").strip("_")
        dest = OUT / "Weimar-Jazz" / f"{slug}.abc"
        if done(dest): continue
        try:
            ev = db.execute("select pitch, bar, beat, tatum, division, num, denom, duration, beatdur from melody where melid=? order by onset", (melid,)).fetchall()
            beats = db.execute("select bar, beat, chord, signature from beats where melid=? order by onset", (melid,)).fetchall()
            ev = [e for e in ev if e[1] is not None and e[1] >= 1]
            num, den = (int(x) for x in (sig or "4/4").split("/")) if sig and "/" in (sig or "") else (4, 4)
            bl = fractions.Fraction(4, den)                               # one beat, in quarter notes
            def pos(bar, beat, tatum, div):
                return ((bar - 1) * num + (beat - 1)) * bl + fractions.Fraction(tatum - 1, max(div, 1)) * bl
            part = stream.Part(); part.append(meter.TimeSignature(f"{num}/{den}"))
            if bpm: part.insert(0, tempo.MetronomeMark(number=round(bpm)))
            try:
                kn = (keyname or "").split("-")[0]
                part.insert(0, m21key.Key(kn.replace("b", "-") if len(kn) > 1 else kn, "minor" if "min" in (keyname or "") else "major"))
            except Exception: pass
            G = fractions.Fraction(1, 12)                                 # snap to 1/12 quarter: 16ths and triplets, nothing MusicXML can't write
            snap = lambda q: round(q / G) * G
            starts = [snap(pos(b, bt, t, d)) for _, b, bt, t, d, *_ in ev]
            for i, (p, b, bt, t, d, n_, de_, dur, bdur) in enumerate(ev):
                st = starts[i]
                grid = fractions.Fraction(1, max(d, 1)) * bl
                want = max(grid, round(fractions.Fraction(dur / bdur).limit_denominator(48) * bl / grid) * grid) if bdur else grid
                nxt = starts[i + 1] if i + 1 < len(starts) else st + want
                ql = snap(min(want, nxt - st) if nxt > st else grid)
                if ql <= 0 or (i and st == starts[i - 1]): continue
                nn = note.Note(int(round(p))); nn.quarterLength = ql
                part.insert(st, nn)
            last = None
            for b, bt, ch, _ in beats:
                if ch and ch != last and b is not None and b >= 1:
                    off = ((b - 1) * num + (bt - 1)) * bl
                    try: cs = harmony.ChordSymbol(ch.replace("j7", "maj7").replace("-", "m").replace("b", "-", 1) if len(ch) > 1 and ch[1] == "b" else ch.replace("j7", "maj7").replace("-", "m"))
                    except Exception: cs = expressions.TextExpression(ch)
                    part.insert(off, cs); last = ch
            sc = stream.Score(); sc.insert(0, part)
            sc.metadata = music21.metadata.Metadata(title=f"{title}{' ' + addon if addon else ''}", composer=f"{perf} ({inst}) solo, transcribed by the Weimar Jazz Database")
            sc.makeNotation(inPlace=True)
            x = TMP / f"wjd_{melid}.musicxml"; sc.write("musicxml", fp=str(x))
            err = x2a(x, dest); x.unlink(missing_ok=True)
            log(stage="weimar", src=f"wjazzd.db melid {melid}", abc=str(dest), error=err)
        except Exception as e:
            log(stage="weimar", src=f"wjazzd.db melid {melid}", abc=str(dest), error=f"{type(e).__name__}: {e}"[:300])
    print("weimar", len(solos))

# ── Billboard: chord charts ───────────────────────────────────────────────────
BB_Q = {"maj": "", "min": "m", "7": "7", "maj7": "maj7", "min7": "m7", "dim": "dim", "aug": "aug", "sus4": "sus4", "sus2": "sus2",
        "maj6": "6", "min6": "m6", "9": "9", "maj9": "maj9", "min9": "m9", "hdim7": "m7b5", "dim7": "dim7", "11": "11", "min11": "m11",
        "13": "13", "5": "5", "1": "", "minmaj7": "m(maj7)", "7(#9)": "7#9", "sus4(b7)": "7sus4", "sus4(b7,9)": "9sus4", "maj(9)": "add9"}
def bb_chord(c):
    if c in ("N", "X", "*", "&pause"): return None
    root, _, q = c.partition(":"); q, _, bass = q.partition("/")
    root = root.replace("b", "b")
    qs = BB_Q.get(q)
    if qs is None: qs = q.replace("min", "m").replace("maj", "maj")
    return root + qs
def billboard():
    idx = {r["id"]: r for r in csv.DictReader(open(CORP / "billboard/index.csv"))}
    for f in sorted((CORP / "billboard/McGill-Billboard").glob("*/salami_chords.txt")):
        sid = f.parent.name.lstrip("0") or "0"; meta = idx.get(sid, {})
        lines = f.read_text(errors="replace").splitlines()
        hdr = {m.group(1): m.group(2).strip() for m in (re.match(r"#\s*(\w+):\s*(.*)", l) for l in lines) if m}
        title, artist = hdr.get("title", meta.get("title", "")), hdr.get("artist", meta.get("artist", ""))
        meter_, tonic = hdr.get("metre", "4/4"), hdr.get("tonic", "C")
        body, sec = [], None
        for l in lines:
            if l.startswith("#"):
                m = re.match(r"#\s*(metre|tonic):\s*(\S+)", l)
                if m and body: body.append(f"[{'M' if m.group(1) == 'metre' else 'K'}:{m.group(2)}]")
                continue
            parts = l.split("\t", 1)
            if len(parts) < 2: continue
            txt = parts[1]
            m = re.match(r"\s*([A-Z]'*),\s*([^,|]+),", txt)
            if m: body.append(f'\n"^{m.group(2).strip()}"'); sec = m.group(2)
            for bar in re.findall(r"\|([^|]*)(?=\|)", txt):
                toks = bar.split()
                if not toks: continue
                num = int(meter_.split("/")[0]) if "/" in meter_ else 4
                odd = re.fullmatch(r"\((\d+)/(\d+)\)", toks[0])       # a bar in another meter: "(2/4) A:maj"
                if odd:
                    toks = toks[1:]; den0 = int(meter_.split("/")[1]) if "/" in meter_ else 4
                    num = fractions.Fraction(int(odd.group(1)) * den0, int(odd.group(2)))
                    body.append(f"[M:{odd.group(1)}/{odd.group(2)}]")
                    if not toks: continue
                n = len(toks)
                cells = []
                for t in toks:
                    if t == ".": cells.append("x"); continue
                    ch = bb_chord(t)
                    cells.append((f'"{ch}"' if ch else "") + "x")
                # each token is an equal share of the bar
                share = fractions.Fraction(num, n)
                body.append([(c, share) for c in cells])
                if odd: body.append(f"[M:{meter_}]")
        if not body: continue
        import math
        k = 1
        for it in body:
            if isinstance(it, list):
                for _, sh in it: k = k * sh.denominator // math.gcd(k, sh.denominator)
        def cell(c, sh): v = sh * k; return c + ("" if v == 1 else str(v))
        body = [(" ".join(cell(c, sh) for c, sh in it) + " |") if isinstance(it, list) else it for it in body]
        den = int(meter_.split("/")[1]) if "/" in meter_ else 4
        meter_l = f"{den * k}"
        abc = (f"X:{sid}\nT:{title}\nC:{artist}\nZ:McGill Billboard Project (CC0); chords only, x = an invisible beat\n"
               f"M:{meter_}\nL:1/{meter_l}\nK:{tonic}\n" + " ".join(body).strip() + "]\n").replace("|]", "|]").replace(" |]", "|]")
        abc = re.sub(r"\|\s*\]$", "|]", abc.rstrip("]\n") + "]") + "\n"
        dest = OUT / "Billboard" / f"{int(sid):04d}_{re.sub(r'[^A-Za-z0-9]+', '_', artist + '_' + title).strip('_')[:80]}.abc"
        dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(abc)
        log(stage="billboard", src=str(f), abc=str(dest), error=None)
    print("billboard done")

# ── check every ABC with abcjs (the site's renderer) ──────────────────────────
CHECK_JS = r"""
global.window = global; global.document = { createElement: () => ({ getContext: () => null, style: {} }) }; global.navigator = { userAgent: "node" };
const A = require(process.argv[2]); const ABCJS = global.ABCJS || A; const fs = require("fs");
const files = fs.readFileSync(0, "utf8").split("\n").filter(Boolean); const out = {};
for (const f of files) { try { const t = ABCJS.parseOnly(fs.readFileSync(f, "utf8")); let w = 0, n = 0; t.forEach(x => { n++; w += (x.warnings || []).length; }); out[f] = [n, w]; } catch (e) { out[f] = [0, -1]; } }
process.stdout.write(JSON.stringify(out));
"""
def check():
    files = [str(p) for p in OUT.rglob("*.abc")]
    js = TMP / "check.js"; TMP.mkdir(parents=True, exist_ok=True); js.write_text(CHECK_JS)
    res = {}
    for i in range(0, len(files), 500):
        r = subprocess.run(["node", str(js), str(SITE / "apps/shared/abcjs-basic.js")], input="\n".join(files[i:i + 500]), capture_output=True, text=True)
        res.update(json.loads(r.stdout or "{}"))
    (OUT / "_abcjs-check.json").write_text(json.dumps({os.path.relpath(k, HOME): v for k, v in res.items()}))
    print("checked", len(res), "files;", sum(1 for v in res.values() if v[1] == 0), "with no warnings")

# ── catalogue ────────────────────────────────────────────────────────────────
def head_of(p):
    t = {"T": "", "C": ""}
    try:
        for l in open(p, errors="replace"):
            if l[:2] in ("T:", "C:") and not t[l[0]]: t[l[0]] = l[2:].strip()
            if l.startswith("K:"): break
    except OSError: pass
    return t

def catalogue():
    chk = json.loads((OUT / "_abcjs-check.json").read_text()) if (OUT / "_abcjs-check.json").exists() else {}
    rows, seen = [], set()
    for l in open(LOG):
        e = json.loads(l)
        key = e.get("abc") or e.get("src")
        if key in seen: continue
        seen.add(key); seen.add(e.get("src"))
        abc = e.get("abc"); ok = abc and done(abc) and not e.get("error")
        src_name = next((n for n in LIC if n in (abc or "")), None) or {"openscore": "OpenScore-Lieder", "dcml": "DCML"}.get(e["stage"], e["stage"])
        h = head_of(abc) if ok else {"T": "", "C": ""}
        c = chk.get(os.path.relpath(abc, HOME)) if ok else None
        rows.append({"source": src_name, "title": h["T"], "composer": h["C"], "abc": os.path.relpath(abc, WIR) if ok and str(abc).startswith(str(WIR)) else (abc if ok else ""),
                     "restricted": "CCARH: research only" if src_name in ("Essen", "Haydn-Quartets", "Beethoven-Sonatas") else "", "source_file": os.path.relpath(e["src"], HOME) if e["src"].startswith(str(HOME)) else e["src"],
                     "status": "in Corpus/" if e.get("skip") else ("converted" if ok else "failed: " + (e.get("error") or "?")[:120]),
                     "tunes": c[0] if c else "", "abcjs_warnings": c[1] if c else "",
                     "licence": LIC.get(src_name, ("", ""))[0]})
    mc = SITE / "scripts/mutopia/catalog.json"
    if mc.exists():
        logged = seen
        for p in json.load(open(mc))["pieces"]:
            if str(MUT / p.get("ly", "")) in logged: continue
            rows.append({"source": "Mutopia", "title": p.get("title", ""), "composer": p.get("composerName") or p.get("composer", ""), "abc": "", "restricted": "",
                         "source_file": "Downloads/mutopia/" + p.get("ly", ""), "status": "not converted: not reached", "tunes": "", "abcjs_warnings": "",
                         "licence": p.get("license", "")})
    with open(OUT / "catalogue.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print("catalogue:", len(rows), "rows"); print(Counter((r["source"], r["status"].split(":")[0]) for r in rows).most_common(40))

# ── Mutopia: LilyPond -> MIDI (exact rhythms) -> music21 -> MusicXML -> xml2abc ──
# MIDI keeps no spelling, slurs, dynamics, articulation or lyrics. Spelling is rebuilt from the key signature (respell);
# a \partial pickup is put back by shifting the music (MIDI starts every piece on a full bar).
MUT_OUT = OUT / "Mutopia"
DUR = {"1": 4, "2": 2, "4": 1, "8": .5, "16": .25, "32": .125}

def ly_fix(t):
    t = re.sub(r"\s+#'([A-Za-z][\w-]*)(?=\s*(?:#'|=))", r".\1", t)            # x #'a #'b = v  ->  x.a.b = v (pre-2.18 syntax)
    t = re.sub(r'\\lyricsto\s*("[^"]*"|[\w.]+)\s*(\\(?:new|context)\s+Lyrics(?:\s*=\s*"?\w+"?)?)', r"\2 \\lyricsto \1", t)
    t = re.sub(r'\\note\s*#"([\d.]+)"', r"\\note { \1 }", t)
    t = re.sub(r"#\s*\(set-octavation\s+(-?\d)\)", r"\\ottava #\1", t)
    t = re.sub(r"(?<=[a-g\d>'),.])([-_^])\|", r"\1!", t)                  # old staccatissimo
    t = re.sub(r"\\applyMusic\s*#unfold-repeats", r"\\unfoldRepeats", t)
    t = re.sub(r"\\on-the-fly\s*#[\w-]+", "", t)
    for a, b in (("\\bigger", "\\larger"), ("\\RemoveEmptyStaffContext", "\\RemoveEmptyStaves"), ("\\sustainDown", "\\sustainOn"),
                 ("\\sustainUp", "\\sustainOff"), ("\\setTextCresc", "\\crescTextCresc"), ("\\fermataMarkup", "\\fermata")):
        t = re.sub(re.escape(a) + r"(?![A-Za-z])", lambda m: b, t)
    return strip_block(t, "paper")                                         # only MIDI is wanted: old page code breaks most often

def strip_block(t, name):
    out, i = [], 0
    for m in re.finditer(r"\\" + name + r"\s*\{", t):
        if m.start() < i: continue
        j, depth = m.end(), 1
        while j < len(t) and depth:
            depth += {"{": 1, "}": -1}.get(t[j], 0); j += 1
        out.append(t[i:m.start()]); i = j
    return "".join(out) + t[i:]

def main_file(src):
    """The file LilyPond should compile: src itself if it has a \\score/\\book, else the file in its folder that includes it."""
    txt = lambda f: f.read_text(errors="replace")
    if re.search(r"\\(score|book)\b", txt(src)): return src
    lys = [f for f in src.parent.glob("*.ly") if f != src]
    inc = [f for f in lys if src.name in txt(f) and re.search(r"\\(score|book)\b", txt(f))]
    alls = inc or [f for f in lys if re.search(r"\\(score|book)\b", txt(f))]
    return alls[0] if len(alls) == 1 or inc else src

def partial_ql(text):
    m = re.search(r"\\partial\s+(\d+)(\.*)(?:\s*\*\s*(\d+)(?:/(\d+))?)?", text)
    if not m or m.group(1) not in DUR: return None
    q = DUR[m.group(1)] * (2 - 0.5 ** len(m.group(2)))
    if m.group(3): q *= int(m.group(3)) / int(m.group(4) or 1)
    return q

def respell(score):
    from music21 import key as K, pitch as P
    for el in score.recurse().notes:
        ks = el.getContextByClass("KeySignature") or K.KeySignature(0)
        dia = {q.pitchClass: q.name for q in ks.asKey("major").getScale().pitches[:7]}
        for p in (el.pitches if el.isChord else [el.pitch]):
            pc, midi = p.pitchClass, p.midi
            if pc in dia: name = dia[pc]
            else:
                up = P.Pitch(dia[(pc - 1) % 12]).transpose("A1").name      # raise the note below
                dn = P.Pitch(dia[(pc + 1) % 12]).transpose("-A1").name     # or lower the note above
                nat = [n for n in (up, dn) if len(n) == 1]
                name = nat[0] if nat else (dn if ks.sharps < 0 or (ks.sharps == 0 and pc == 10) else up)
            p.name = name
            while p.midi < midi: p.octave += 1
            while p.midi > midi: p.octave -= 1

def mut_dest(piece):
    folder = pathlib.Path(piece["ly"]).parent
    if folder.name.endswith("-lys"): folder = folder.parent                 # the piece's own folder: unique, unlike notes.ly
    return MUT_OUT / (piece.get("composer") or "unknown") / (folder.name + ".abc")

def _mut_job(piece):
    import music21, warnings; warnings.filterwarnings("ignore")
    src = MUT / piece["ly"]
    try: src = main_file(src)
    except OSError: pass
    dest = mut_dest(piece)
    if done(dest): return (str(src), str(dest), None)
    TMP.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP) as td:
        try:
            work = pathlib.Path(td) / "w"; shutil.copytree(src.parent, work)
            lys = list(work.rglob("*.ly")) + list(work.rglob("*.ily"))
            for f in lys: subprocess.run(["convert-ly", "-e", "-q", str(f)], capture_output=True, timeout=120)
            for f in lys: f.write_text(ly_fix(f.read_text(errors="replace")))
            main = work / src.name; text = main.read_text(errors="replace")
            if "\\midi" not in "".join(f.read_text(errors="replace") for f in lys):
                main.write_text(re.sub(r"\\layout\s*\{", r"\\midi { } \\layout {", text))
            r = subprocess.run(["lilypond", "-s", "-dno-print-pages", "-o", str(pathlib.Path(td) / "out"), main.name],
                               cwd=work, capture_output=True, text=True, timeout=600)
            mids = sorted(pathlib.Path(td).glob("out*.mid*"), key=lambda m: (len(m.name), m.name))
            if not mids: return (str(src), str(dest), "LilyPond made no MIDI: " + (re.findall(r"error: .*", r.stderr) or [r.stderr[-200:]])[0][:200])
            pq = partial_ql("".join(f.read_text(errors="replace") for f in lys))
            abcs = []
            for n, mid in enumerate(mids):
                sc = music21.converter.parse(str(mid), quantizePost=True, quarterLengthDivisors=(4, 3))
                ts = sc.recurse().getElementsByClass("TimeSignature").first()
                if pq and ts and n == 0 and pq < ts.barDuration.quarterLength:
                    shift = ts.barDuration.quarterLength - pq
                    for part in sc.parts:
                        fl = part.flatten()
                        new = music21.stream.Part()
                        for el in fl.getElementsByClass(["TimeSignature", "KeySignature", "MetronomeMark", "Instrument"]):
                            new.insert(0 if el.offset == 0 else el.offset + shift, el)
                        for el in fl.notes: new.insert(el.offset + shift, el)
                        sc.replace(part, new)
                    sc = sc.makeNotation()
                    for part in sc.parts:
                        m1 = part.getElementsByClass("Measure").first()
                        if m1:
                            for r_ in list(m1.recurse().getElementsByClass("Rest")):
                                if r_.offset < shift: r_.activeSite.remove(r_)
                            m1.paddingLeft = shift
                respell(sc)
                t = piece.get("title") or src.stem
                sc.metadata = music21.metadata.Metadata(title=t + (f" ({n + 1})" if len(mids) > 1 else ""),
                                                        composer=piece.get("composerName") or piece.get("composer") or "")
                x = pathlib.Path(td) / f"m{n}.musicxml"; sc.write("musicxml", fp=str(x))
                a = pathlib.Path(td) / f"m{n}.abc"; err = x2a(x, a)
                if err: return (str(src), str(dest), "xml2abc: " + err[-200:])
                abcs.append(re.sub(r"^(T:.*\n)\1+", r"\1", re.sub(r"^X:\s*\d+", f"X:{n + 1}", a.read_text(), flags=re.M), flags=re.M))
            dest.parent.mkdir(parents=True, exist_ok=True)
            hdr = f"% {piece.get('title', '')}: Mutopia Project {piece.get('page', '')}\n% Licence: {piece.get('license', '?')}. From LilyPond via MIDI: no slurs, dynamics, articulation or lyrics; spelling rebuilt from the key.\n\n"
            dest.write_text(hdr + "\n".join(abcs))
            return (str(src), str(dest), None)
        except subprocess.TimeoutExpired: return (str(src), str(dest), "timeout")
        except Exception as e: return (str(src), str(dest), f"{type(e).__name__}: {e}"[:300])

def mutopia(limit=None):
    pieces = json.load(open(SITE / "scripts/mutopia/catalog.json"))["pieces"]
    if limit: pieces = pieces[:limit]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for i, (piece, (src, dest, err)) in enumerate(zip(pieces, ex.map(_mut_job, pieces, chunksize=1))):
            log(stage="mutopia", src=str(MUT / piece["ly"]), abc=dest, error=err)
            if i % 100 == 0: print("mutopia", i, "/", len(pieces), flush=True)
    print("mutopia", len(pieces))

STAGES = {"openscore": openscore, "dcml": dcml, "sapp": sapp, "local": local, "nottingham": nottingham, "weimar": weimar,
          "billboard": billboard, "mutopia": mutopia, "check": check, "catalogue": catalogue}
if __name__ == "__main__":
    for s in (sys.argv[1:] or list(STAGES)):
        STAGES[s]()
