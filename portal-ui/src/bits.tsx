import type { ComponentProps, ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { Verdict } from './findings';
import { initials, mins, type Seen, type Student } from './types';

/* The berkeleyhaas.me vocabulary: one flat bordered card, small caps-free type, colour only
   when it means something (state tints, SectionA green for presence, gold for the camera). */

export function Card({ className, ...props }: ComponentProps<'div'>) {
  return <div className={cn('min-w-0 rounded-xl border border-line bg-raised p-4', className)} {...props} />;
}

const badgeVariants = cva('inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xxs font-semibold', {
  variants: {
    tone: {
      good: 'bg-good-tint text-good', warn: 'bg-warn-tint text-warn', bad: 'bg-bad-tint text-bad',
      neutral: 'bg-surface text-muted-foreground', course: 'bg-course-tint text-course', people: 'bg-people-tint text-people',
      career: 'bg-career-tint text-career', claude: 'bg-claude-tint text-claude',
    },
  },
  defaultVariants: { tone: 'neutral' },
});
export function Badge({ className, tone, ...props }: ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

const verdictTone: Record<Verdict, 'good' | 'warn' | 'neutral' | 'bad'> = { ready: 'good', partly: 'warn', no: 'neutral', never: 'bad' };
const verdictText: Record<Verdict, string> = { ready: 'Works', partly: 'Partly', no: 'Not yet', never: 'Don’t' };
export const VerdictBadge = ({ v }: { v: Verdict }) => <Badge tone={verdictTone[v]}>{verdictText[v]}</Badge>;

export function Face({ s, size = 'size-8', className }: { s: Pick<Student, 'name' | 'photo'>; size?: string; className?: string }) {
  return (
    <span className={cn('relative inline-flex shrink-0 overflow-hidden rounded-full bg-surface', size, className)}>
      <img src={s.photo} alt="" className="size-full object-cover" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
      <span className="absolute inset-0 -z-10 flex items-center justify-center text-xxs text-muted-foreground">{initials(s.name)}</span>
    </span>
  );
}

/** A student's presence in one class: a filled square sized by time on camera. */
export function PresenceDot({ seen, comments = 0 }: { seen?: Seen; comments?: number }) {
  const sec = seen?.seconds ?? 0;
  const tone = !sec ? 'bg-surface border border-dashed border-line-strong' : !seen!.present ? 'bg-warn/50' : sec >= 120 ? 'bg-oski' : sec >= 30 ? 'bg-oski/70' : 'bg-oski/40';
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1">
          <span className={cn('inline-block size-3.5 rounded-[4px]', tone)} />
          {comments > 0 && <span className="text-xxs font-semibold tabular-nums text-course">{comments}</span>}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {!sec ? 'Not recognised on camera' : `${seen!.present ? 'Present' : 'Glimpsed only'} · ${mins(sec)} on camera${seen!.first ? ` · ${seen!.first}–${seen!.last}` : ''}`}
        {comments > 0 && ` · ${comments} named comment${comments > 1 ? 's' : ''}`}
      </TooltipContent>
    </Tooltip>
  );
}

export function Heading({ title, desc, right }: { title: ReactNode; desc?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {desc && <p className="mt-0.5 max-w-3xl text-sm text-muted-foreground">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

/** Inline facts in a sentence-like row instead of big number cards. */
export function Facts({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
      {items.map(([v, l], i) => <span key={i} className="text-muted-foreground"><b className="font-semibold tabular-nums text-foreground">{v}</b> {l}</span>)}
    </div>
  );
}

/** Stable colour per student, for the timeline and anywhere a voice is drawn. */
export function voiceColour(name: string) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `oklch(0.66 0.14 ${h})`;
}
