# Choreographing a chart

A chart is a dance for the fingers, and the keyboard is a simplified MIDI keyboard: each
key press answers a note you can hear, each lane is a register, and a hold is a sustained
note. The code can hear (melody, drums, sections, loudness), see (pictures of the chart and
the video) and check (playability). **You decide how the fingers should move.**

## What a good chart feels like

- **It answers the music.** Every note is something audible: a sung note (or the strings'
  line where they are louder than the voice), a kick, a snare.
  Where the music rests, the chart rests. A note with nothing to hear nearby feels random.
- **It has a shape that repeats.** Pick a small vocabulary of rhythm cells for a section
  (for example "downbeat, and-of-2, beat 4") and reuse it. When the music repeats (the
  inspect text says `like m12(0.8)`), repeat the same finger pattern, then vary it at the end
  of the phrase. Regularity is what makes a chart readable; randomness is the enemy.
- **A reprise gets the same dance.** When the inspect header lists
  `repeats: m41-54 again at m97-110`, the chorus (or verse) is sung again. Choreograph the
  first time carefully, then copy it with `{"repeat": {"from": [41, 54], "to": 97}}` and only
  change the measures where the singing really differs (the per-measure lines show both). A
  player should recognise the chorus with their fingers the second time.
- **The second half deserves the same care as the first.** The `section ...` lines in the
  header show how much of the singing each section answers. Keep that even across the song;
  a late section far below the first chorus will feel like the chart lost the song.
- **The fingers follow the melody's contour.** Higher notes sit further right (lanes 1-7 =
  low to high). A rising line is a stair going right, a falling line goes left, a repeated
  pitch is a repeated lane (at most twice in a row on easier charts). Prefer stairs, mirrors
  and repeated figures over leaps. Keep consecutive notes within about three lanes.
- **Hands make sense.** Lanes 1-3 are the left hand (S D F), lane 4 is the thumb on the
  space bar, lanes 5-7 are the right hand (J K L). Let the thumb carry the beat (kick) and
  let hands alternate on runs.
- **Drums are the backbone, the melody is the voice.** Kick and snare on strong beats give a
  steady pulse; sung notes ride on top. On easy charts let the voice lead and keep one or two
  drum anchors per measure; on harder charts add more of the drum pattern.
- **Long sung notes are holds.** A held vowel becomes a hold on the lane of its pitch, and
  the hold ends when the vowel ends (not on a convenient grid line). While a hold is down,
  play only single notes with the other hand. A held note played as a single tap, with
  something else pressed over the rest of it, reads as "the singer was ignored".
- **The peak gets the most care.** The loudest measures (`e8`, `e9`) and the longest held
  notes are where the song means the most: a belted, sustained high note is the emotional
  climax, and the chart must show it (a hold for its whole length, the lane of its pitch,
  nothing busy competing with it). A chart can be 95% "answered" and still miss its climax.
- **Whoever is loudest leads.** Where the strings, guitar or piano are louder than the voice
  (an instrumental intro, a bridge, the outro) the `melody` lines are theirs: follow them,
  do not leave those measures empty or fill them with drums alone. A measure that inspect
  shows as `(silent)` while the music is loud (`e5` or more) means something was not heard:
  look at the video and `analyze_video_notes` before accepting it.
- **Drums only where a drummer plays.** The draft already drops drum hits from measures
  where the drum stem is only leakage from the other instruments. If a quiet, drumless verse
  (`e0`-`e2`) still shows steady kick and snare in your chart, that is leakage: remove it.
- **Energy has an arc.** Use the loudness (`eN`) and the sections: sparse and simple in a
  quiet verse, fuller in the chorus. A repeated section should feel like itself.

## Difficulty

Ask the player where they are. Many cannot play Medium comfortably: if they say a chart is
too hard, lower the density (thin the busy sections, keep the downbeats, the holds on long
vowels and the climax) instead of leaving it as the target says.

Density targets in notes per second (the stats show where a chart stands):
Beginner ~0.9, Easy ~1.4, Medium ~2.3, Hard ~3.3. Easier charts use fewer lanes at a time,
longer gaps, steps of one or two lanes, and no jumps. Harder charts add 16th-note runs,
jumps (two lanes at once, only where melody and drum hit together), and more holds. If an
easy chart plays harder than its target, thin it out instead of keeping every sung note.

## Working method

1. Read the whole song's shape: `inspect_chart` header (sections, loudness) and
   `look_at_video` for the mood.
2. Work section by section. `inspect_chart` a section, `view_chart` it, plan the rhythm cell
   and lane contour, then write the measures with `edit_chart`.
3. Reuse: write one good measure, `copy` it to the measures that sound like it, and
   `repeat` whole reprised sections, then adjust.
4. Read `warnings` after every edit and fix them (density, reach, unsupported notes, long
   sung notes not played as holds).
5. `view_chart` again; if it still looks scattered, simplify. Finish with a pass over the
   whole chart checking that repeated music got repeated patterns and that late sections
   answer the singing as well as early ones.
6. Audit before you finish. The "answers N% of the sung notes" figures do not catch a held
   vowel played as one tap, so check these yourself:
   - the `long sung notes (4+ beats) not played as holds: m40@2/20 ...` line in the
     `inspect_chart` header (and in the `warnings`): give each one a hold, starting with the
     longest and the loudest. Easy and above only; Beginner charts have no holds.
   - the loudest sections (highest `eN`): view them, and read their sustained notes
     (`NAME@SLOT/LENGTH` with a length of 8 or more) against the chart.
   - the sections without singing (intro, bridges, outro): they must follow whoever leads
     (strings, piano...), not sit empty.
   - the build warnings: "onsets drift ... check sync" means the tempo may vary or the beat
     grid is off; a chart on a shifted grid feels wrong everywhere, so fix the offset
     (`adjust_song_offset`) before polishing notes.
7. Last, `align_chart`: it moves every note onto the exact attack it answers and ends holds
   with the voice, without changing your choreography. Run it again after any later edit.

## Notation

`s4:3` tap on lane 3 at slot 4 (a measure has 16 slots, s0 is the downbeat, s4 is beat 2),
`s8:2+6` jump, `s8:H3` hold starts, `s12:|3` hold ends. Edits: `{"measure": 5, "notes": "..."}`,
`{"copy": {"from": 5, "to": [9, 13]}}`, `{"repeat": {"from": [41, 54], "to": 97}}`, `{"clear": [20]}`.
