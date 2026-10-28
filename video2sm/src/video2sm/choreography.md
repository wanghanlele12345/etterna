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
  play only single notes with the other hand.
- **Energy has an arc.** Use the loudness (`eN`) and the sections: sparse and simple in a
  quiet verse, fuller in the chorus. A repeated section should feel like itself.

## Difficulty

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
4. Read `warnings` after every edit and fix them (density, reach, unsupported notes).
5. `view_chart` again; if it still looks scattered, simplify. Finish with a pass over the
   whole chart checking that repeated music got repeated patterns and that late sections
   answer the singing as well as early ones.
6. Last, `align_chart`: it moves every note onto the exact attack it answers and ends holds
   with the voice, without changing your choreography. Run it again after any later edit.

## Notation

`s4:3` tap on lane 3 at slot 4 (a measure has 16 slots, s0 is the downbeat, s4 is beat 2),
`s8:2+6` jump, `s8:H3` hold starts, `s12:|3` hold ends. Edits: `{"measure": 5, "notes": "..."}`,
`{"copy": {"from": 5, "to": [9, 13]}}`, `{"repeat": {"from": [41, 54], "to": 97}}`, `{"clear": [20]}`.
