import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge, Facts, PresenceDot, voiceColour } from './bits';
import { WhoIsThis } from './labels';
import { PlayButton } from './player';
import { day, mins, type Portal, type Student } from './types';

export default function StudentSheet({ d, s, onClose, reload }: { d: Portal; s: Student | null; onClose: () => void; reload: () => Promise<void> }) {
  const mine = s ? d.comments.filter((c) => c.student_id === s.id) : [];
  const calls = s ? d.sessions.flatMap((x) => x.calls.filter((c) => c.student_id === s.id).map((c) => ({ ...c, date: x.date }))) : [];
  return (
    <Sheet open={!!s} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="sheet-in w-full gap-0 p-0 sm:max-w-xl">
        {s && (
          <>
            <SheetHeader className="flex-row items-center gap-4 border-b border-line p-5">
              <img src={s.photo} alt={s.name} className="size-16 rounded-xl object-cover" />
              <div className="min-w-0 space-y-1">
                <SheetTitle className="flex items-center gap-2 text-lg">
                  {s.name}{s.voiceprint && <span className="inline-block size-2.5 rounded-full" style={{ background: voiceColour(s.name) }} title="Voice learned" />}
                </SheetTitle>
                <SheetDescription>{d.course} · {d.section}{s.team ? ` · Team ${s.team}` : ''}</SheetDescription>
                <Facts items={[[`${s.sessions_present}/${d.sessions.length}`, 'classes'], [mins(s.seconds_total), 'on camera'], [s.comments, 'comments'], [s.called, 'called on']]} />
              </div>
            </SheetHeader>
            <ScrollArea className="h-[calc(100vh-7.5rem)]">
              <div className="space-y-6 p-5">
                <section className="space-y-2">
                  <h3 className="text-sm font-semibold">In class</h3>
                  <div className="grid grid-cols-5 gap-2">
                    {d.sessions.map((x) => {
                      const a = s.attendance[x.date];
                      const n = mine.filter((c) => c.date === x.date).length;
                      return (
                        <div key={x.date} className="space-y-1 text-center">
                          {a?.tile ? <img src={a.tile} alt={`${s.name} on ${day(x.date)}`} className="aspect-square w-full rounded-lg object-cover" />
                            : <div className="flex aspect-square items-center justify-center rounded-lg border border-dashed border-line-strong text-xxs text-muted-foreground">not seen</div>}
                          <div className="flex items-center justify-center gap-1.5"><PresenceDot seen={a} comments={n} /></div>
                          <div className="text-xxs text-muted-foreground">{day(x.date).replace(/^\w+, /, '')}</div>
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-xxs text-muted-foreground">The face shown is the camera’s best match that day. A glimpse (amber) can be someone else.</p>
                </section>

                <section className="space-y-2">
                  <h3 className="text-sm font-semibold">What they said <span className="font-normal text-muted-foreground">({mine.length})</span></h3>
                  {mine.length === 0 && <p className="text-sm text-muted-foreground">Nothing named yet. Comments are named after a professor call, a voice match, or a label.</p>}
                  {mine.map((c, i) => (
                    <div key={i} className="flex gap-3 rounded-xl border border-line p-3">
                      <PlayButton clip={{ date: c.date, start: c.start, end: c.end, title: s.name, sub: c.text.slice(0, 60) }} />
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex flex-wrap items-center gap-1.5 text-xxs text-muted-foreground">
                          <span className="font-medium text-foreground">{day(c.date)} · {c.at}</span><span>{mins(c.seconds)}</span>
                          <Badge tone={c.how === 'voice match' ? 'neutral' : c.how === 'you labelled' ? 'good' : 'course'}>{c.how}{c.confidence ? ` ${c.confidence}` : ''}</Badge>
                          {c.score && <Badge tone="career">rated {c.score.mean.toFixed(1)}/5</Badge>}
                          {c.how === 'voice match' && !c.seen_that_day && <Badge tone="warn">check: not on camera that day</Badge>}
                        </div>
                        <p className="text-sm leading-relaxed">{c.text}</p>
                        {c.how !== 'you labelled' && <WhoIsThis roster={d.roster} reload={reload} spans={[{ date: c.date, start: c.start, end: c.end }]} size="xs" label="Not them?" />}
                      </div>
                    </div>
                  ))}
                </section>

                {calls.length > 0 && (
                  <section className="space-y-2">
                    <h3 className="text-sm font-semibold">Called on by the professor</h3>
                    {calls.map((c, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <PlayButton clip={{ date: c.date, start: Math.max(0, c.t - 6), end: c.t + 20, title: `Calling on ${s.name}`, sub: 'professor’s call and the reply' }} />
                        <span className="shrink-0 text-muted-foreground">{day(c.date)} {c.at}</span><span className="truncate">“…{c.text}”</span>
                      </div>
                    ))}
                  </section>
                )}
              </div>
            </ScrollArea>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
