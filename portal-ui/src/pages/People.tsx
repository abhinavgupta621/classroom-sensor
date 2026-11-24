import { useMemo, useState } from 'react';
import { ArrowDown, Fingerprint } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Badge, Card, Face, Facts, Heading, PresenceDot } from '../bits';
import { PlayButton } from '../player';
import { day, mins, type Portal, type Student } from '../types';

type Filter = 'all' | 'quiet' | 'spoke' | 'patchy' | 'never' | 'check';
type Sort = 'name' | 'classes' | 'camera' | 'comments' | 'talk';

const FILTERS: [Filter, string, string][] = [
  ['all', 'Everyone', ''],
  ['spoke', 'Spoke', 'At least one named comment'],
  ['quiet', 'Present, never named', 'Recognised in 3+ classes, no comment named yet'],
  ['patchy', 'Patchy', 'Recognised in 1–2 classes'],
  ['never', 'Never seen', 'Not recognised in any class'],
  ['check', 'To check', 'Voice matches from a class they weren’t seen in'],
];

export default function People({ d, openStudent }: { d: Portal; openStudent: (s: Student) => void }) {
  const [q, setQ] = useState('');
  const [f, setF] = useState<Filter>('all');
  const [sort, setSort] = useState<Sort>('name');
  const dates = d.sessions.map((s) => s.date);
  const perClass = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of d.comments) m.set(c.student_id + c.date, (m.get(c.student_id + c.date) ?? 0) + 1);
    return m;
  }, [d.comments]);
  const longest = useMemo(() => {
    const m = new Map<string, (typeof d.comments)[number]>();
    for (const c of d.comments) if (!m.has(c.student_id) || m.get(c.student_id)!.seconds < c.seconds) m.set(c.student_id, c);
    return m;
  }, [d.comments]);

  const counts: Record<Filter, number> = {
    all: d.roster.length,
    spoke: d.roster.filter((s) => s.comments > 0).length,
    quiet: d.roster.filter((s) => s.sessions_present >= 3 && s.comments === 0).length,
    patchy: d.roster.filter((s) => s.sessions_present > 0 && s.sessions_present < 3).length,
    never: d.roster.filter((s) => s.sessions_present === 0).length,
    check: d.roster.filter((s) => s.comments_to_check > 0).length,
  };
  const rows = useMemo(() => {
    let r = d.roster.filter((s) => s.name.toLowerCase().includes(q.toLowerCase()));
    r = r.filter((s) => f === 'all' || (f === 'spoke' ? s.comments > 0 : f === 'quiet' ? s.sessions_present >= 3 && s.comments === 0
      : f === 'patchy' ? s.sessions_present > 0 && s.sessions_present < 3 : f === 'never' ? s.sessions_present === 0 : s.comments_to_check > 0));
    const key: Record<Sort, (s: Student) => number> = { name: () => 0, classes: (s) => s.sessions_present * 1e6 + s.seconds_total, camera: (s) => s.seconds_total, comments: (s) => s.comments, talk: (s) => s.talk_seconds };
    return [...r].sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name) : key[sort](b) - key[sort](a));
  }, [d.roster, q, f, sort]);

  const Th = ({ k, children, className }: { k: Sort; children: React.ReactNode; className?: string }) => (
    <th className={cn('px-2 py-2 text-xxs font-semibold text-muted-foreground', className)}>
      <button onClick={() => setSort(k)} className={cn('inline-flex items-center gap-0.5 hover:text-foreground', sort === k && 'text-foreground')}>
        {children}{sort === k && <ArrowDown className="size-3" />}
      </button>
    </th>
  );

  return (
    <div className="page-in space-y-4">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight">People</h1>
        <Facts items={[
          [`${d.roster.filter((s) => s.sessions_present > 0).length}/${d.roster.length}`, 'recognised in at least one class'],
          [`${d.roster.filter((s) => s.sessions_present >= 4).length}`, 'in 4–5 of 5 classes'],
          [`${counts.spoke}`, 'named speaking'],
          [`${d.voices.learned.length}`, 'voices learned'],
        ]} />
      </div>
      <Card className="space-y-3 p-0">
        <div className="flex flex-wrap items-center gap-2 p-4 pb-0">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name" className="h-8 w-48 rounded-md border border-line bg-raised px-2.5 text-sm outline-none focus:border-focus" />
          {FILTERS.map(([k, l, tip]) => (
            <button key={k} title={tip} onClick={() => setF(k)}
              className={cn('h-8 rounded-full border px-3 text-sm transition-colors', f === k ? 'border-foreground bg-foreground text-background' : 'border-line hover:bg-surface')}>
              {l} <span className="tabular-nums opacity-60">{counts[k]}</span>
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-y border-line bg-surface/60">
              <tr className="text-left">
                <Th k="name" className="pl-4">Student</Th>
                {dates.map((x) => <th key={x} className="px-2 py-2 text-center text-xxs font-semibold text-muted-foreground">{day(x).replace(/^\w+, /, '')}</th>)}
                <Th k="classes" className="text-right">Classes</Th>
                <Th k="camera" className="text-right">On camera</Th>
                <Th k="comments" className="text-right">Comments</Th>
                <Th k="talk" className="text-right">Talk</Th>
                <th className="px-2 py-2 text-xxs font-semibold text-muted-foreground">Voice</th>
                <th className="w-10 pr-4" />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const c = longest.get(s.id);
                return (
                  <tr key={s.id} className="cursor-pointer border-b border-line/60 transition-colors hover:bg-surface/70" onClick={() => openStudent(s)}>
                    <td className="py-1.5 pl-4 pr-2">
                      <div className="flex items-center gap-2.5"><Face s={s} />
                        <div className="min-w-0"><div className="truncate font-medium">{s.name}</div>{s.team && <div className="text-xxs text-muted-foreground">Team {s.team}</div>}</div>
                      </div>
                    </td>
                    {dates.map((x) => <td key={x} className="px-2 text-center"><PresenceDot seen={s.attendance[x]} comments={perClass.get(s.id + x)} /></td>)}
                    <td className="px-2 text-right tabular-nums">{s.sessions_present}/{dates.length}</td>
                    <td className="px-2 text-right tabular-nums text-muted-foreground">{s.seconds_total ? mins(s.seconds_total) : '–'}</td>
                    <td className="px-2 text-right tabular-nums">{s.comments || <span className="text-muted-foreground">–</span>}{s.comments_to_check > 0 && <Badge tone="warn" className="ml-1">{s.comments_to_check}?</Badge>}</td>
                    <td className="px-2 text-right tabular-nums text-muted-foreground">{s.talk_seconds ? mins(s.talk_seconds) : '–'}</td>
                    <td className="px-2">{s.voiceprint ? <Badge tone="course"><Fingerprint className="size-3" />learned</Badge> : null}</td>
                    <td className="pr-4">{c && <PlayButton clip={{ date: c.date, start: c.start, end: c.end, title: s.name, sub: 'longest comment' }} />}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 pb-4 text-xxs text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="inline-block size-3 rounded-[3px] bg-oski" />on camera 2 min+</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-3 rounded-[3px] bg-oski/40" />present (3 s+)</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-3 rounded-[3px] bg-warn/50" />glimpsed only</span>
          <span className="flex items-center gap-1.5"><span className="inline-block size-3 rounded-[3px] border border-dashed border-line-strong" />not seen (not the same as absent)</span>
          <span className="flex items-center gap-1.5"><b className="text-course">2</b> named comments that class</span>
        </div>
      </Card>
      <Heading title="" desc="Comments count only what’s named: professor calls, voice matches and your labels. Most student talk isn’t named yet, so absence of comments isn’t silence." />
    </div>
  );
}
