# What is not converted, and why (updated 2026-10-22)

## Not converted
| What | Why | To do it |
|---|---|---|
| **Mutopia: 181 of 1,881 failed** (1,689 converted, to `Mutopia/<composer>/<piece>.abc`) | LilyPond 2.26 can't compile them, even after `convert-ly` and the fixes in `ly_fix`. Main causes: no error message, mostly multi-file pieces where the main file wasn't found (52); old Scheme in page layout or music (24); bar checks written straight after articulations, `f-\|` (23); old context names such as `Engraver` and `Thread` (17); the editor's own commands, such as `\hinst` (7). Each reason is in the `status` column. | Fix by hand, or add more rules to `ly_fix`. |
| Mutopia: 11 rows "not reached" | A catalogue entry whose file path is shared with another entry. | |
| Mutopia count gap | The clone gives 1,881 pieces with headers; mutopiaproject.org lists 2,124. | Some pieces have no `mutopiatitle` header in the clone, or are multi-file; not traced. |
| **The Session** | Its licence prohibits LLM processing. Left untouched for you to decide. | Your call; it is ABC already. |
| **Isophonics** (Beatles) | Annotations are timed in seconds only, with no bars, so there is nothing to put on a staff. | Would need beat tracking against the recordings. |
| music21 corpus, Woodwind Fingering Guide, Iowa samples, VSL | Not downloaded (see `~/Downloads/corpora/README.md`). | |

## Failed files (21, all DCML: MuseScore 4 will not export them, in batch or alone)
Each is listed in `_convert-log.jsonl` with "MuseScore did not export". The MS3 and reviewed copies of the same pieces:
Mozart K533-3; Bach BWV1007 Sarabande; Beethoven sonata 02-4; Dvořák Silhouettes op8 no8; Schütz SWV298;
Liszt Pèlerinage 161.04, 161.05, 161.07, 162.03; Monteverdi 8-18; W.F. Bach F002 n07a.
Try opening them in MuseScore 3, or exporting by hand.

## abcjs warnings (`_abcjs-check.json`: [tunes, warnings] per file)
Most are harmless:
- `$` line-break marks from xml2abc: abcjs ignores them. This accounts for nearly all of DCML (2,254 of 2,297).
- `[I:staff +1]` cross-staff moves, plus `!ped!` and `!ped-up!`: unknown to abcjs and dropped. Pedal marks and cross-staff notes are lost.
- Grace notes holding chords (`{[..]}`): the grace notes are dropped.

- **Mutopia files lose a lot (LilyPond → MIDI → music21 → MusicXML → xml2abc):** no slurs, dynamics, articulation, ornaments, lyrics or fingering.
  Spelling is rebuilt from the key (a note outside the key: natural if possible, else flats in flat keys, sharps in sharp keys), so chromatic passages may be misspelled.
  Pickups (`\partial`) are put back only for the first one in a piece. Grace notes become short notes. 322 of 1,689 have abcjs warnings: tuplet rests and durations that can't be written.

Worth looking at before using a file:
- **Beethoven-Sonatas** (77 of 103): "Duration not representable" in some music21 Humdrum imports. Check the bar lengths.
- **Weimar-Jazz** (288 of 456): stray `x` inside tuplets after quantising to 1/12 of a beat. The notes are right, but the rests may look odd.
- **Nottingham** (5): the errors are in the original files.
- **Billboard** (24): chord-only charts; uncommon meters left over.

Fixed in this run: Billboard meter changes and fractional beats; Weimar durations that MusicXML can't write (all 456 solos convert now);
OpenScore paths containing `[ ]`; MuseScore batch jobs that stopped partway (now retried one file at a time).
