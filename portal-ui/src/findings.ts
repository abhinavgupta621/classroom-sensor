// Everything measured in the pilot, Nov 23 2026, on one course section's recordings. Kept as data so
// the pages stay in step with the write-up.

export type Verdict = 'ready' | 'partly' | 'no' | 'never';

export const timings: { step: string; time: string; note: string }[] = [
  { step: 'Download a class from Panopto', time: '~1 min', note: 'Room camera plus audio' },
  { step: 'Find when the camera is on students', time: '~35 s', note: 'One low-resolution pass' },
  { step: 'Attendance, fast (a few frames per shot)', time: '~1 min', note: 'Finds ~86% of what the full scan finds, no wrong names' },
  { step: 'Attendance, full (every second)', time: '8–12 min', note: 'A few more students' },
  { step: 'Transcript (Mac GPU, large-v3-turbo)', time: '~7 min', note: '17× real time; CPU small model 15 min' },
  { step: 'Voiceprints for every comment', time: '~1 min', note: 'SpeechBrain ECAPA' },
  { step: 'Name voices (name calls + voiceprints)', time: 'seconds', note: '' },
  { step: 'Professor vs student split', time: '~5 min', note: 'Window-level, measured under load' },
  { step: 'Read desk name cards', time: '~7 min', note: 'Optional; few readable' },
  { step: 'Class gallery and room views', time: '~15 s', note: '' },
  { step: 'Summary, questions, review sheet', time: '1–2 min', note: 'Claude' },
  { step: 'Rate contributions', time: '~1 min', note: 'Claude' },
  { step: 'Everything, fast path', time: '10–12 min', note: 'Per 2-hour class, one Mac' },
];

export const accuracy: { area: string; metric: string; result: string; basis: string; verdict: Verdict }[] = [
  { area: 'Faces', metric: 'Wrong names at threshold 0.50 (Oct 8, 1080p)', result: '0 of 1,393', basis: 'Matches to other sections are certainly wrong', verdict: 'ready' },
  { area: 'Faces', metric: 'Same seat, seconds apart, same name', result: '744 of 744', basis: 'Consistency', verdict: 'ready' },
  { area: 'Faces', metric: 'Wrong-section people, 5 classes, ≥3 s rule', result: '3 total', basis: '~2% of names estimated wrong at 576p', verdict: 'ready' },
  { area: 'Attendance', metric: 'Students named per class (≥3 s)', result: '33–42 of 58', basis: 'True attendance unknown', verdict: 'partly' },
  { area: 'Attendance', metric: 'Seen in at least one of 5 classes', result: '55 of 58', basis: '≥3 s on camera', verdict: 'ready' },
  { area: 'Attendance', metric: 'Fast scan vs full scan', result: '37 of 43 in 57 s', basis: '3 frames per camera shot', verdict: 'ready' },
  { area: 'Camera', metric: 'Time the camera shows students', result: '11–33% of class', basis: 'Oct 8 low (game day), others 23–33%', verdict: 'partly' },
  { area: 'Camera', metric: 'Speaker in the shot', result: '8 of 9', basis: 'Known speakers', verdict: 'ready' },
  { area: 'Camera', metric: 'Visual cue picks the speaker (gaze, centre, size, lips)', result: '0–1 of 8', basis: '~16 faces per shot', verdict: 'no' },
  { area: 'Name cards', metric: 'Cards readable', result: '5 of 58 students', basis: 'All 309 readings correct', verdict: 'partly' },
  { area: 'Transcript', metric: 'Professor speech clean', result: '~95%', basis: 'Claude review of the transcript', verdict: 'ready' },
  { area: 'Transcript', metric: 'Called names spelled right', result: '4 → 9–10 of 10', basis: 'Class list as hints', verdict: 'ready' },
  { area: 'Voices', metric: 'Same class, held-out comment, right student', result: '11 of 11', basis: '8 speakers', verdict: 'ready' },
  { area: 'Voices', metric: 'Other classes, right student', result: '6 of 6', basis: 'Name at end of the professor’s sentence', verdict: 'partly' },
  { area: 'Voices', metric: 'Student talk named by voice so far', result: '14–30% per class', basis: '16 voiceprints after 5 classes; grows', verdict: 'partly' },
  { area: 'Voices', metric: 'Professor vs student, mislabelled turns', result: '12 of 32 → ~5', basis: 'Window-level professor print', verdict: 'partly' },
  { area: 'AI rating', metric: 'Same scores across two runs', result: '124 of 128', basis: 'Not yet checked by a professor', verdict: 'partly' },
];

export const can: { what: string; how: string; verdict: Verdict }[] = [
  { what: 'Who was definitely there', how: '33–42 of 58 per class, almost no wrong names', verdict: 'ready' },
  { what: 'Who shows up across the term', how: '55 of 58 seen in 5 classes', verdict: 'ready' },
  { what: 'Whole-class gallery: faces, time on camera, first and last seen', how: 'Every class', verdict: 'ready' },
  { what: 'Transcript with names spelled right', how: 'Class list as hints', verdict: 'ready' },
  { what: 'Who spoke when the professor called them', how: 'Name at the end of his sentence, next voice', verdict: 'ready' },
  { what: 'Name other comments by voice', how: '14–30% of student talk now; grows each class', verdict: 'partly' },
  { what: 'Professor talk time, questions, class timeline', how: 'From audio and transcript', verdict: 'ready' },
  { what: 'Summary, questions asked, exam review, follow-up email', how: 'Claude, 1–2 min', verdict: 'ready' },
  { what: 'Rate comments', how: 'Consistent; a suggestion until a professor checks it', verdict: 'partly' },
  { what: 'Who was absent', how: 'Camera doesn’t see everyone every class; no real attendance to check', verdict: 'partly' },
  { what: 'Late arrival, early exit', how: 'Camera isn’t on the class at the start and end', verdict: 'no' },
  { what: 'Pick the speaker from faces', how: '~16 faces per shot; cues fail at this size', verdict: 'no' },
  { what: 'One picture of the whole room', how: 'Camera presets don’t line up; partial panorama only', verdict: 'partly' },
  { what: 'Emotion or attention from faces', how: 'Weak science; banned in EU education', verdict: 'never' },
  { what: 'Public rankings or automatic grades', how: 'Suggestions to the professor only', verdict: 'never' },
];

export const needs: { need: string; fixes: string; cost: string }[] = [
  { need: 'Real attendance for 3–5 classes (TA tick sheet, once)', fixes: 'Proves accuracy, including absences', cost: 'A few TA hours' },
  { need: 'Haas AV: log of which desk mic was pressed', fixes: 'Who is talking, from the mic seat', cost: 'Probably free if logged' },
  { need: 'Haas AV: full-resolution recordings every class', fixes: 'Sharper faces (4 of 5 classes were 1024×576)', cost: 'A recorder setting' },
  { need: 'A fixed camera on the class', fixes: 'Everyone seen all class; late and early', cost: '$1.4k–4.3k a room' },
  { need: 'Ceiling mic array (if no mic log)', fixes: 'Where each voice comes from', cost: '$4k–7.6k a room' },
  { need: 'Panopto admin access', fixes: 'Pull recordings automatically; pick the camera feed by content', cost: 'Setup' },
  { need: 'A professor checks 20–30 ratings', fixes: 'Proves participation ratings', cost: '~1 hour' },
  { need: 'P4-approved storage and a GPU server', fixes: 'Run on Berkeley systems', cost: 'Campus service, ~$0.10 a class' },
];

export const lessons = [
  'Recognising faces is solved; the challenge is seeing everyone and knowing who is talking.',
  'Many classes beat one: attendance coverage and voiceprints both improve with every class.',
  'Panopto swaps its camera and slides labels between classes; pick the camera by what’s in the picture.',
  'The camera turns to a student when their mic is pressed: the speaker is in the shot 8 times in 9.',
  'Names the professor calls at the end of a sentence ("…Sam, go.") reliably label the next voice.',
  'Giving the transcriber the class list fixes most name spellings.',
  'It’s cheap and fast: about a minute for attendance, about 7 minutes for the transcript.',
];
