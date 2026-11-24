import { HOSTED } from '../hosted';
import { useState } from 'react';
import { AudioLines, Fingerprint, Hand, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge, Card, Face, Facts, Heading, voiceColour } from '../bits';
import { WhoIsThis } from '../labels';
import { PlayButton } from '../player';
import { day, mins, type Portal, type Student } from '../types';

export default function Voices({ d, openStudent, reload }: { d: Portal; openStudent: (s: Student) => void; reload: () => Promise<void> }) {
  const [tab, setTab] = useState<'unknown' | 'learned'>('unknown');
  const byName = Object.fromEntries(d.roster.map((r) => [r.name, r]));
  const v = d.voices;
  const unknownSecs = v.unknown.reduce((a, g) => a + g.seconds, 0);
  return (
    <div className="page-in space-y-5">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">Voices</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          A voice gets a name four ways: the professor ends a sentence with it (“…Sam, go.”) and the next voice is that student; those clips
          become a voiceprint; the student’s other comments in every class are matched to it; and a person names the rest in the
          instructor’s copy of this portal, which re-matches every class in about a second.
        </p>
        <Facts items={[
          [`${v.learned.length}/${d.roster.length}`, 'voices learned'],
          [d.comments.length, 'comments named'],
          [v.unknown_total, `unknown voice groups (${mins(unknownSecs)} in the top ${v.unknown.length})`],
          [v.labels, 'labels so far'],
        ]} />
      </div>

      <div className="flex gap-1 border-b border-line">
        {([['unknown', `Unknown voices`, v.unknown_total], ['learned', 'Learned voices', v.learned.length]] as const).map(([k, l, n]) => (
          <button key={k} onClick={() => setTab(k)} className={cn('-mb-px border-b-2 px-3 py-2 text-sm transition-colors', tab === k ? 'border-foreground font-semibold' : 'border-transparent text-muted-foreground hover:text-foreground')}>
            {l} <span className="tabular-nums opacity-60">{n}</span>
          </button>
        ))}
      </div>

      {tab === 'unknown' && (
        <>
          <Heading title="" desc={HOSTED ? 'Student-side audio nobody is named for yet, grouped by how alike it sounds, biggest first. Naming a group happens in the local portal and covers every clip in it, across all classes.' : 'Student-side audio nobody is named for yet, grouped by how alike it sounds, biggest first. Play a clip or two, then say who it is. Your answer covers every clip in the group, across all classes.'} />
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[repeat(2,minmax(0,1fr))]">
            {v.unknown.map((g, gi) => {
              const sug = g.suggestion ? byName[g.suggestion.student] : null;
              return (
                <Card key={g.id} className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 font-semibold"><AudioLines className="size-4 text-gold" />Voice {gi + 1}</div>
                      <div className="text-xxs text-muted-foreground">{g.turns} clips · {mins(g.seconds)} · {g.classes} {g.classes === 1 ? 'class' : 'classes'}</div>
                    </div>
                    <WhoIsThis roster={d.roster} reload={reload} suggestion={g.suggestion?.student} spans={g.spans} />
                  </div>
                  {sug && (
                    <button onClick={() => openStudent(sug)} className="flex w-full items-center gap-2 rounded-lg border border-dashed border-line-strong p-2 text-left text-xxs hover:bg-surface">
                      <Sparkles className="size-3.5 text-gold" />Sounds a little like <Face s={sug} size="size-5" /><b>{sug.name}</b>
                      <span className="text-muted-foreground">similarity {g.suggestion!.similarity}</span>
                    </button>
                  )}
                  <div className="space-y-2">
                    {g.clips.map((c) => (
                      <div key={c.date + c.start} className="flex items-start gap-2.5">
                        <PlayButton clip={{ date: c.date, start: c.start, end: c.end, title: `Voice ${gi + 1}`, sub: 'unknown voice' }} />
                        <div className="min-w-0 text-sm">
                          <div className="text-xxs text-muted-foreground">{day(c.date)} · {c.at} · {mins(c.end - c.start)}</div>
                          <p className="line-clamp-2">{c.text}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              );
            })}
          </div>
        </>
      )}

      {tab === 'learned' && (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-[repeat(2,minmax(0,1fr))] lg:grid-cols-[repeat(3,minmax(0,1fr))]">
          {v.learned.map((l) => {
            const s = byName[l.student];
            return (
              <Card key={l.student} className="space-y-3">
                <button className="flex items-center gap-3 text-left" onClick={() => s && openStudent(s)}>
                  {s && <span className="rounded-full p-0.5" style={{ background: voiceColour(l.student) }}><Face s={s} size="size-10" /></span>}
                  <div>
                    <div className="font-medium">{l.student}</div>
                    <div className="flex flex-wrap gap-1 pt-1">
                      {l.anchors - l.manual > 0 && <Badge tone="course"><Hand className="size-3" />{l.anchors - l.manual} called</Badge>}
                      {l.manual > 0 && <Badge tone="good"><Fingerprint className="size-3" />{l.manual} by you</Badge>}
                      <Badge><AudioLines className="size-3" />{l.matches} matched</Badge>
                    </div>
                  </div>
                </button>
                <div className="space-y-1.5">
                  {l.samples.map((c) => (
                    <div key={c.date + c.start} className="flex items-start gap-2">
                      <PlayButton clip={{ date: c.date, start: c.start, end: c.end, title: l.student, sub: 'voiceprint sample' }} />
                      <div className="min-w-0 text-xxs"><div className="text-muted-foreground">{day(c.date)}</div><p className="line-clamp-1 text-sm">{c.text}</p></div>
                    </div>
                  ))}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
