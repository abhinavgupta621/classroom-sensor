import { useEffect, useState } from 'react';
import { Badge, Card, Heading, VerdictBadge } from '../bits';
import { accuracy, can, needs, timings } from '../findings';
import type { Portal } from '../types';

const QUESTIONS: { q: string; a: string; v: 'ready' | 'partly' | 'no' }[] = [
  { q: 'Can existing recordings tell us who attended?', a: 'Who was there, yes: 33–42 of 58 named per class with ~2% wrong at 576p, 0 wrong at 1080p. Who was absent, not yet: the camera doesn’t look at everyone every class and we have no ground truth.', v: 'partly' },
  { q: 'Can we tell who spoke?', a: 'When the professor calls a name, yes, and that seeds voiceprints that matched 6 of 6 held-out comments in other classes. From video alone, no: among ~16 faces no visual cue picked the speaker.', v: 'partly' },
  { q: 'Can we measure contribution quality?', a: 'A rubric applied by Claude is consistent (124 of 128 identical across runs). Whether it agrees with the professor is untested.', v: 'partly' },
  { q: 'Can it run cheaply and quickly?', a: 'Yes: attendance in ~1 minute and a transcript in ~7 minutes per 2-hour class on one Mac; ~$0.10 a class on a GPU server (estimate).', v: 'ready' },
];

const ISSUES = [
  ['Panopto swaps feed labels', 'The stream called “camera” was the slides in 4 of 5 classes. The camera has to be picked by what’s in the picture.'],
  ['Resolution varies', 'Oct 8 is 1920×1080; the other four are 1024×576, so faces are ~30 px instead of ~57 px and errors rise.'],
  ['Pre-class music and breaks', 'Songs are transcribed as “student” speech. Trimmed automatically in three classes; label the rest as “Not a student”.'],
  ['Guests and the TA', 'A guest speaker (Oct 6) and the game scorekeeper count as non-professor audio until labelled.'],
  ['Professor vs student at turn boundaries', 'Pause-split turns merge a student’s last words with the professor’s reply; window-level voiceprints fix about two thirds.'],
  ['One section, one room, five classes', 'Every number here is from one section of one course. Treat them as a first look, not a validated rate.'],
];

const ETHICS = [
  ['Consent', 'Collected by the administration this year for face, voiceprint and all-party recording.'],
  ['Data level', 'Face templates are P4 at Berkeley; joined to attendance, the dataset is P4. Today it lives on one Mac.'],
  ['FERPA', 'Per-student attendance and participation are education records; professors should own them.'],
  ['Publishing research', 'Needs human-subjects review (CPHS) separately from operational consent.'],
  ['Never', 'Emotion or attention inference (banned in EU education since Feb 2025), public rankings, automatic grades.'],
];

import { HOSTED } from '../hosted';

export default function Method({ d }: { d: Portal }) {
  const [frame, setFrame] = useState(HOSTED ? '/tagged-2026-10-08.jpg' : `/frame?${Date.now()}`);
  useEffect(() => { if (HOSTED) return; const id = setInterval(() => setFrame(`/frame?${Date.now()}`), 5000); return () => clearInterval(id); }, []);
  return (
    <div className="page-in mx-auto max-w-5xl space-y-10">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Method and findings</h1>
        <p className="text-sm text-muted-foreground">Automated attendance and participation from existing Panopto recordings. {d.course}, {d.section}: {d.roster.length} students, {d.sessions.length} classes (Sep 22 – Oct 8, 2026). Built Nov 2026 by Abhinav Gupta and Tess Rubin.</p>
      </div>

      <section className="space-y-3">
        <Heading title="Research questions" />
        <div className="grid gap-3 md:grid-cols-2">
          {QUESTIONS.map((x) => (
            <Card key={x.q} className="space-y-1.5">
              <div className="flex items-start justify-between gap-3"><div className="font-medium">{x.q}</div><VerdictBadge v={x.v} /></div>
              <p className="text-sm text-muted-foreground">{x.a}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <Heading title="Pipeline" desc="Per 2-hour class, one Mac, nothing else running." />
        <Card className="p-0">
          <table className="w-full text-sm">
            <tbody>
              {timings.map((t) => (
                <tr key={t.step} className="border-b border-line/60 last:border-0">
                  <td className="py-2 pl-4 pr-3 font-medium">{t.step}</td>
                  <td className="whitespace-nowrap px-3 tabular-nums">{t.time}</td>
                  <td className="py-2 pl-3 pr-4 text-muted-foreground">{t.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      <section className="space-y-3">
        <Heading title="Results" desc="Wrong face names are counted by matching against all four the core course sections: a match to another section is certainly wrong." />
        <Card className="p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-surface/60 text-left text-xxs text-muted-foreground">
              <tr><th className="py-2 pl-4 font-semibold">Area</th><th className="px-3 font-semibold">Measure</th><th className="px-3 font-semibold">Result</th><th className="px-3 font-semibold">Basis</th><th className="pr-4" /></tr>
            </thead>
            <tbody>
              {accuracy.map((a) => (
                <tr key={a.metric} className="border-b border-line/60 last:border-0 align-top">
                  <td className="py-2 pl-4 font-medium">{a.area}</td>
                  <td className="px-3 py-2">{a.metric}</td>
                  <td className="px-3 py-2 font-semibold tabular-nums">{a.result}</td>
                  <td className="px-3 py-2 text-muted-foreground">{a.basis}</td>
                  <td className="py-2 pr-4"><VerdictBadge v={a.verdict} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <Heading title="Data issues found" />
          <Card className="space-y-3">{ISSUES.map(([h, t]) => <div key={h}><div className="text-sm font-medium">{h}</div><p className="text-sm text-muted-foreground">{t}</p></div>)}</Card>
        </div>
        <div className="space-y-3">
          <Heading title="What the face model sees" desc={HOSTED ? "The busiest student shot on Oct 8. Green: named (0.50+). Amber: a face it can’t name." : "A random moment from Oct 8 every few seconds. Green: named (0.50+). Amber: a face it can’t name."} />
          <Card className="p-2"><img src={frame} alt="Annotated camera frame" className="w-full rounded-lg" /></Card>
        </div>
      </section>

      <section className="space-y-3">
        <Heading title="What’s possible" />
        <div className="grid gap-3 md:grid-cols-2">
          {(['ready', 'partly', 'no', 'never'] as const).map((v) => (
            <Card key={v} className="space-y-2.5">
              <VerdictBadge v={v} />
              {can.filter((c) => c.verdict === v).map((c) => <div key={c.what}><div className="text-sm font-medium">{c.what}</div><div className="text-sm text-muted-foreground">{c.how}</div></div>)}
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <Heading title="What it would take" desc="Cheapest first; the first three need no new hardware." />
        <Card className="p-0">
          <table className="w-full text-sm"><tbody>
            {needs.map((n) => (
              <tr key={n.need} className="border-b border-line/60 last:border-0 align-top">
                <td className="py-2 pl-4 pr-3 font-medium">{n.need}</td><td className="px-3 py-2">{n.fixes}</td><td className="py-2 pl-3 pr-4 text-muted-foreground">{n.cost}</td>
              </tr>
            ))}
          </tbody></table>
        </Card>
      </section>

      <section className="space-y-3">
        <Heading title="Ethics and data handling" />
        <Card className="space-y-2.5">{ETHICS.map(([h, t]) => <div key={h} className="flex gap-3 text-sm"><Badge className="mt-0.5 w-24 justify-center">{h}</Badge><span>{t}</span></div>)}</Card>
      </section>
    </div>
  );
}
