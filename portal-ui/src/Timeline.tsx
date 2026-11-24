import { useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { voiceColour } from './bits';
import { usePlayer } from './player';
import type { Row, Session, Student } from './types';

const clock = (s: number) => `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}`;
const clockS = (s: number) => `${clock(s)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

type Hover = { x: number; t: number; label: string } | null;

/** The whole class on one line per signal. Click anywhere to listen from that moment. */
export default function Timeline({ s, rows, roster, onStudent }: { s: Session; rows: Row[]; roster: Student[]; onStudent: (st: Student) => void }) {
  const p = usePlayer();
  const box = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Hover>(null);
  const D = s.duration || 7200;
  const pct = (t: number) => `${(t / D) * 100}%`;
  const w = (a: number, b: number) => `${Math.max(0.12, ((b - a) / D) * 100)}%`;
  const byName = useMemo(() => Object.fromEntries(roster.map((r) => [r.name, r])), [roster]);
  const prof = rows.filter((r) => r.role === 'professor');
  const stud = rows.filter((r) => r.role === 'student');
  const ticks = Array.from({ length: Math.floor(D / 900) + 1 }, (_, i) => i * 900);
  const playing = p.clip?.date === s.date;

  // Time under the pointer, measured against the first bar track (the label column is narrower on phones).
  const at = (e: React.MouseEvent) => {
    const r = box.current!.querySelector('[data-bar]')!.getBoundingClientRect();
    return Math.max(0, Math.min(D, ((e.clientX - r.left) / r.width) * D));
  };
  const show = (e: React.MouseEvent) => { const t = at(e); setHover({ x: e.clientX - box.current!.getBoundingClientRect().left, t, label: describe(t) }); };
  const describe = (t: number) => {
    const row = rows.find((x) => t >= x.start && t <= x.end && x.role !== 'preclass');
    const call = s.calls.find((c) => Math.abs(c.t - t) < D / 300);
    if (call) return `Called on ${call.student}`;
    if (!row) return t < s.class_start ? 'Before class' : 'Quiet';
    return row.speaker ?? (row.role === 'professor' ? 'Professor' : 'Unknown student');
  };

  const Track = ({ label, children, h = 'h-5' }: { label: string; children: React.ReactNode; h?: string }) => (
    <div className="grid grid-cols-[var(--lab)_minmax(0,1fr)] items-center gap-2 sm:gap-3">
      <div className="truncate text-right text-xxs font-medium text-muted-foreground">{label}</div>
      <div data-bar className={cn('relative rounded-[4px] bg-surface', h)}>{children}</div>
    </div>
  );

  return (
    <div className="space-y-1.5 select-none [--lab:4.25rem] sm:[--lab:7.5rem]">
      <div ref={box} className="relative cursor-pointer space-y-1.5"
        onMouseMove={show}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => { show(e); p.play({ date: s.date, start: at(e), title: 'Whole class', sub: 'from the timeline', mode: 'class' }); }}>
        {/* Not part of the click target: the label column */}
        <Track label="Camera on class">
          {s.class_start > 0 && <div className="track-bar bg-line/60" style={{ left: 0, width: pct(s.class_start) }} />}
          {s.camera.map(([a, b], i) => <div key={i} className="track-bar bg-gold" style={{ left: pct(a), width: w(a, b) }} />)}
        </Track>
        <Track label="Professor">
          {prof.map((r, i) => <div key={i} className="track-bar bg-foreground/70" style={{ left: pct(r.start), width: w(r.start, r.end) }} />)}
        </Track>
        <Track label="Students" h="h-7">
          {stud.map((r, i) => (
            <div key={i} className={cn('track-bar', !r.speaker && 'bg-muted-foreground/35')}
              style={{ left: pct(r.start), width: w(r.start, r.end), background: r.speaker ? voiceColour(r.speaker) : undefined }} />
          ))}
        </Track>
        <Track label="Called on">
          {s.calls.map((c, i) => (
            <button key={i} className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-raised bg-course"
              style={{ left: pct(c.t) }} aria-label={`Called on ${c.student}`}
              onClick={(e) => { e.stopPropagation(); const st = byName[c.student]; if (st) onStudent(st); }} />
          ))}
        </Track>
        {hover && (
          <>
            <div className="pointer-events-none absolute inset-y-0 w-px bg-focus/60" style={{ left: hover.x }} />
            <div className="pointer-events-none absolute -top-7 z-10 -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-raised px-2 py-0.5 text-xxs shadow-[var(--shadow-pop)]"
              style={{ left: Math.min(Math.max(60, hover.x), (box.current?.clientWidth ?? 9999) - 60) }}>{clockS(hover.t)} · {hover.label}</div>
          </>
        )}
        {playing && <div className="pointer-events-none absolute inset-y-0 w-0.5 rounded bg-focus" style={{ left: `calc(var(--lab) + 0.75rem + (100% - var(--lab) - 0.75rem) * ${p.time / D})` }} />}
      </div>
      <div className="grid grid-cols-[var(--lab)_minmax(0,1fr)] gap-2 sm:gap-3">
        <span />
        <div className="relative h-4 text-xxs text-muted-foreground">
          {ticks.map((t) => <span key={t} className="absolute -translate-x-1/2 tabular-nums" style={{ left: pct(t) }}>{clock(t)}</span>)}
        </div>
      </div>
    </div>
  );
}
