# Scores: other corpora as ABC

Scores from outside the When in Rome analyses, converted to ABC for everything-music-site, by
`Code/convert_scores_abc.py` (from the downloads in `~/Downloads/corpora` and `~/Downloads/mutopia`; it resumes where it stopped).

- `catalogue.csv`: every piece from every source (Mutopia included), with its ABC file, status, licence, and abcjs check
  (`tunes`, `abcjs_warnings`: abcjs, the site's renderer, parsing the file; 0 warnings = clean).
- `UNDONE.md`: what is not converted, and why.
- `_convert-log.jsonl`, `_abcjs-check.json`: the raw run log and check results.

| Folder | Source | Licence |
|---|---|---|
| OpenScore-Lieder, OpenScore-StringQuartets | OpenScore (MuseScore) | CC0 |
| DCML/<corpus> | Digital and Cognitive Musicology Lab, EPFL | CC BY-NC-SA 4.0 |
| Sapp-Mozart-Sonatas, Sapp-Bach-Chorales | Craig Stuart Sapp (Humdrum) | CC BY-NC-SA 4.0 |
| Nottingham | Nottingham Music Database (jukedeck cleanup) | GPL-3.0 (LICENSE.md inside) |
| Mutopia/<composer> | Mutopia Project (LilyPond) | per piece, in each file's header comment (public domain, CC BY-SA, CC BY) |
| Weimar-Jazz | Weimar Jazz Database, Jazzomat Research Project | ODbL 1.0 / DbCL 1.0 |
| Billboard | McGill Billboard Project: chords only, `x` = an invisible beat | CC0 (please cite Burgoyne, Wild & Fujinaga, ISMIR 2011) |
| **Essen, Haydn-Quartets, Beethoven-Sonatas** | **CCARH** | **Personal research use only: see CCARH-RESTRICTED.md** |

**This repository must stay private while the CCARH folders are in it.** Their licence forbids derivative editions and
using them in teaching materials, free or not; nothing from them goes into the site.

Pieces already converted under `Corpus/` (see `Corpus/corpus_with_abc.csv`) are not converted again; the catalogue lists
them with status `in Corpus/`.

Conversion routes: MusicXML → xml2abc (Wim Vree, v177); MuseScore → MuseScore 4 → MusicXML → xml2abc; Humdrum → music21 →
MusicXML → xml2abc; Weimar → music21 (onsets quantised to the database's own beat grid) → xml2abc; Billboard → written directly; Mutopia → convert-ly + fixes → LilyPond 2.26 MIDI → music21 (respelt to the key) → MusicXML → xml2abc.
Run with `~/Downloads/corpora/_tools/venv/bin/python` (it has music21).
