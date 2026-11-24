import { HOSTED, PUBLIC } from '../hosted';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Headphones, Maximize2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';
import { Badge, Card, Face, Facts, Heading, voiceColour } from '../bits';
import { WhoIsThis } from '../labels';
import { PlayButton, usePlayer } from '../player';
import Timeline from '../Timeline';
import { day, mins, type Portal, type Student } from '../types';

export default function Sessions({ d, openStudent, reload }: { d: Portal; openStudent: (s: Student) => void; reload: () => Promise<void> }) {
  const [date, setDate] = useState(() => new URLSearchParams(location.hash.split('?')[1]).get('d') ?? d.sessions.at(-1)!.date);
  const s = d.sessions.find((x) => x.date === date) ?? d.sessions.at(-1)!;
  const rows = d.transcripts[s.date] ?? [];
  const [zoom, setZoom] = useState<string | null>(null);
  const present = d.roster.filter((r) => r.attendance[s.date]?.present).sort((a, b) => b.attendance[s.date].seconds - a.attendance[s.date].seconds);
  const glimpsed = d.roster.filter((r) => { const a = r.attendance[s.date]; return a && a.seconds > 0 && !a.present; });
  const unseen = d.roster.filter((r) => !(r.attendance[s.date]?.seconds));
  const spoke = new Map<string, number>();
  for (const c of d.comments) if (c.date === s.date) spoke.set(c.student, (spoke.get(c.student) ?? 0) + 1);
  const studentSecs = rows.filter((r) => r.role === 'student').reduce((a, r) => a + r.end - r.start, 0);
  const namedSecs = rows.filter((r) => r.role === 'student' && r.speaker).reduce((a, r) => a + r.end - r.start, 0);
  const camSecs = s.camera.reduce((a, [x, y]) => a + y - x, 0);

  return (
    <div className="grid gap-6 lg:grid-cols-[13rem_1fr]">
      {/* Classes */}
      <nav className="space-y-1 lg:sticky lg:top-20 lg:self-start">
        <div className="px-2 pb-1 text-xxs font-semibold uppercase tracking-wide text-muted-foreground">Classes</div>
        <div className="flex gap-1 overflow-x-auto lg:flex-col">
          {d.sessions.map((x) => (
            <button key={x.date} onClick={() => setDate(x.date)}
              className={cn('shrink-0 rounded-lg px-3 py-2 text-left transition-colors hover:bg-surface', x.date === s.date && 'bg-accent-tint')}>
              <div className="text-sm font-medium">{day(x.date)}</div>
              <div className="text-xxs text-muted-foreground">{x.present_3s} recognised · {x.calls.length} called on</div>
            </button>
          ))}
        </div>
      </nav>

      <div key={s.date} className="page-in min-w-0 space-y-6">
        <div className="space-y-2">
          <h1 className="text-xl font-semibold tracking-tight">{d.course} · {day(s.date)}</h1>
          <Facts items={[
            [`${s.present_3s}/${d.roster.length}`, 'recognised on camera'],
            [`${Math.round((camSecs / s.duration) * 100)}%`, 'of class with the camera on students'],
            [`${s.professor_minutes}m`, 'professor speaking'],
            [`${Math.round(studentSecs / 60)}m`, 'student-side audio'],
            [`${Math.round((namedSecs / Math.max(1, studentSecs)) * 100)}%`, 'of it named'],
            [s.resolution?.replace(',', '×') ?? '–', 'video'],
          ]} />
        </div>

        <Card className="space-y-4 pt-9">
          <Timeline s={s} rows={rows} roster={d.roster} onStudent={openStudent} />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-xxs text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-4 rounded-sm bg-gold" />camera on students</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-4 rounded-sm bg-foreground/70" />professor</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-4 rounded-sm" style={{ background: 'linear-gradient(90deg, oklch(0.66 0.14 30), oklch(0.66 0.14 160), oklch(0.66 0.14 280))' }} />named student (one colour each)</span>
            <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-4 rounded-sm bg-muted-foreground/35" />unknown student voice</span>
            <span className="flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-course" />professor calls a name</span>
            <span className="ml-auto">{PUBLIC ? 'Hover to see who was speaking' : 'Hover to read, click to listen from there'}</span>
          </div>
        </Card>

        <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
          <TranscriptPanel d={d} date={s.date} openStudent={openStudent} reload={reload} />
          <div className="space-y-6">
            <Card className="space-y-3">
              <Heading title={`Who was there`} desc={`${present.length} recognised, ${glimpsed.length} glimpsed, ${unseen.length} not seen. Not seen isn’t absent.`} />
              <div className="grid grid-cols-4 gap-2">
                {present.map((r) => {
                  const a = r.attendance[s.date];
                  return (
                    <button key={r.id} onClick={() => openStudent(r)} className="group space-y-1 text-left" title={`${r.name} · ${mins(a.seconds)} on camera`}>
                      <div className="relative">
                        <img src={a.tile ?? r.photo} alt={r.name} className="aspect-square w-full rounded-lg object-cover transition group-hover:opacity-90" />
                        {spoke.get(r.name) && <span className="absolute right-1 top-1 rounded-full bg-course px-1.5 text-xxs font-semibold text-white">{spoke.get(r.name)}</span>}
                      </div>
                      <div className="truncate text-xxs font-medium">{r.name.split(' ')[0]}</div>
                    </button>
                  );
                })}
              </div>
              {unseen.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-xxs font-medium text-muted-foreground">Not seen on camera ({unseen.length})</summary>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {unseen.map((r) => <button key={r.id} onClick={() => openStudent(r)} className="flex items-center gap-1.5 rounded-full border border-line py-0.5 pl-0.5 pr-2 text-xxs hover:bg-surface"><Face s={r} size="size-5" />{r.name}</button>)}
                  </div>
                </details>
              )}
            </Card>
            <Card className="space-y-3">
              <Heading title="The room" desc={`${s.rooms.length} camera positions showed students.`} />
              {s.panorama && <button onClick={() => setZoom(s.panorama!)} className="group relative block w-full"><img src={s.panorama} alt="Panorama of part of the room" className="w-full rounded-lg" /><Maximize2 className="absolute right-2 top-2 size-4 text-white opacity-0 drop-shadow group-hover:opacity-100" /></button>}
              <div className="grid grid-cols-3 gap-1.5">
                {s.rooms.map((r) => <button key={r.preset} onClick={() => setZoom(r.image)}><img src={r.image} alt={`Camera view ${r.preset}, ${r.faces} faces`} className="aspect-video w-full rounded-md object-cover hover:opacity-90" /></button>)}
              </div>
            </Card>
          </div>
        </div>
      </div>
      <Dialog open={!!zoom} onOpenChange={(o) => !o && setZoom(null)}>
        <DialogContent className="max-w-[95vw] sm:max-w-6xl"><DialogTitle className="sr-only">Camera view</DialogTitle>{zoom && <img src={zoom} alt="" className="w-full rounded-md" />}</DialogContent>
      </Dialog>
    </div>
  );
}

function TranscriptPanel({ d, date, openStudent, reload }: { d: Portal; date: string; openStudent: (s: Student) => void; reload: () => Promise<void> }) {
  const [who, setWho] = useState<'all' | 'student' | 'named'>('all');
  const [q, setQ] = useState('');
  const p = usePlayer();
  const byName = Object.fromEntries(d.roster.map((r) => [r.name, r]));
  const rows = useMemo(() => (d.transcripts[date] ?? []).filter((r) =>
    (who === 'all' || (who === 'student' ? r.role === 'student' : !!r.speaker)) && r.text.toLowerCase().includes(q.toLowerCase())), [d, date, who, q]);
  const following = p.clip?.date === date && p.clip.mode === 'class';
  const live = following ? rows.findIndex((r) => p.time >= r.start - 0.2 && p.time < r.end + 0.5) : -1;
  const list = useRef<HTMLDivElement>(null);
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  useEffect(() => {
    const el = refs.current[live], box = list.current;
    if (el && box) box.scrollTo({ top: el.offsetTop - box.clientHeight / 2, behavior: 'smooth' });
  }, [live]);
  const label = (r: (typeof rows)[number]) => r.speaker ?? (r.role === 'professor' ? (PUBLIC ? 'Instructor' : `Prof. ${d.professor.split(' ').at(-1)}`) : r.role === 'student' ? 'Unknown student' : r.role === 'preclass' ? 'Before class' : '');

  return (
    <Card className="flex min-h-0 flex-col gap-3 p-0">
      <div className="space-y-2 p-4 pb-0">
        <Heading title="Transcript" desc={PUBLIC ? 'Who spoke, when and for how long, with each comment’s rubric score. What was said is withheld in the public edition.' : HOSTED ? '▶ plays a line. Listen to the class and it follows along.' : '▶ plays a line. Listen to the class and it follows along. Name an unknown student and every class learns that voice.'}
          right={PUBLIC ? undefined : <Button size="sm" onClick={() => p.play({ date, start: rows.find((r) => r.role !== 'preclass')?.start ?? 0, title: `Whole class, ${day(date)}`, sub: 'following along', mode: 'class' })}><Headphones />Listen</Button>} />
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup type="single" value={who} onValueChange={(v) => v && setWho(v as typeof who)} variant="outline" size="sm">
            <ToggleGroupItem value="all">Everything</ToggleGroupItem>
            <ToggleGroupItem value="student">Students</ToggleGroupItem>
            <ToggleGroupItem value="named">Named</ToggleGroupItem>
          </ToggleGroup>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search words" className="h-8 w-40 rounded-md border border-line bg-raised px-2.5 text-sm outline-none focus:border-focus" />
        </div>
      </div>
      <div ref={list} className="relative max-h-[38rem] overflow-y-auto border-t border-line">
        {rows.map((r, i) => (
          <div key={i} ref={(el) => { refs.current[i] = el; }}
            className={cn('group grid grid-cols-[1.75rem_3.75rem_8rem_1fr] items-start gap-2.5 border-b border-line/60 px-4 py-2 text-sm transition-colors',
              r.role === 'preclass' && 'italic text-muted-foreground', i === live && 'bg-accent-tint')}>
            {r.role !== 'preclass' ? <PlayButton clip={{ date, start: r.start, end: r.end, title: label(r), sub: r.text.slice(0, 60) }} /> : <span />}
            <button className="pt-1 text-left font-mono text-xxs text-muted-foreground hover:text-foreground" title="Listen from here"
              onClick={() => p.play({ date, start: r.start, title: `Whole class, ${day(date)}`, sub: 'following along', mode: 'class' })}>{r.at}</button>
            <div className="space-y-1 pt-0.5">
              {r.speaker ? (
                <button className="flex items-center gap-1.5 text-left text-xs font-medium hover:underline" onClick={() => byName[r.speaker!] && openStudent(byName[r.speaker!])}>
                  <span className="inline-block size-2 shrink-0 rounded-full" style={{ background: voiceColour(r.speaker) }} />{r.speaker}
                </button>
              ) : <span className={cn('text-xs font-medium', r.role !== 'professor' && 'text-muted-foreground')}>{label(r)}</span>}
              {r.how && <Badge tone={r.how === 'voice match' ? 'neutral' : 'course'}>{r.how}{r.confidence ? ` ${r.confidence}` : ''}</Badge>}
              {r.role === 'student' && (
                <div className={cn(r.speaker && 'opacity-0 group-hover:opacity-100')}>
                  <WhoIsThis roster={d.roster} reload={reload} spans={[{ date, start: r.start, end: r.end }]} size="xs" label={r.speaker ? 'Wrong?' : 'Who?'} />
                </div>
              )}
            </div>
            <p className="pt-0.5 leading-relaxed">{r.text}</p>
          </div>
        ))}
        {rows.length === 0 && <div className="p-6 text-sm text-muted-foreground">Nothing matches.</div>}
      </div>
    </Card>
  );
}
