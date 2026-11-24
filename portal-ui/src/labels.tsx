import { useState } from 'react';
import { Check, UserRound, Ban, GraduationCap } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Face } from './bits';
import type { Student } from './types';
import { HOSTED } from './hosted';

export type Span = { date: string; start: number; end: number };
type Kind = 'student' | 'not_student' | 'professor';

/** Save who is speaking in one or more clips, then wait for the portal to rebuild and reload. */
export async function saveLabels(spans: Span[], kind: Kind, student: string | null, reload: () => Promise<void>) {
  const id = toast.loading(kind === 'student' ? `Saving: ${student}` : kind === 'professor' ? 'Saving: professor' : 'Saving: not a student');
  try {
    const r = await fetch('/api/label', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ spans, kind, student }) });
    if (!r.ok) throw new Error(r.statusText);
    toast.loading('Saved. Re-matching voices across all classes…', { id });
    for (let i = 0; i < 60; i++) {
      await new Promise((res) => setTimeout(res, 1000));
      const st = await (await fetch('/api/rebuild')).json();
      if (!st.running) break;
    }
    await reload();
    toast.success(kind === 'student' ? `Learned ${student}’s voice. Every class is updated.` : 'Saved. Every class is updated.', { id });
  } catch (e) {
    toast.error(`Couldn’t save: ${e}`, { id });
  }
}

export function WhoIsThis({ roster, spans, reload, suggestion, label = 'Who is this?', size = 'sm' }:
  { roster: Student[]; spans: Span[]; reload: () => Promise<void>; suggestion?: string | null; label?: string; size?: 'sm' | 'xs' }) {
  const [open, setOpen] = useState(false);
  if (HOSTED) return null;
  const pick = (kind: Kind, student: string | null) => { setOpen(false); void saveLabels(spans, kind, student, reload); };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="secondary" size="sm" className={size === 'xs' ? 'h-6 px-2 text-xs' : ''} onClick={(e) => e.stopPropagation()}>
          <UserRound />{label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start" onClick={(e) => e.stopPropagation()}>
        <Command>
          <CommandInput placeholder="Type a student’s name…" />
          <CommandList>
            <CommandEmpty>No student with that name.</CommandEmpty>
            {suggestion && (
              <CommandGroup heading="Best guess">
                {roster.filter((r) => r.name === suggestion).map((r) => (
                  <CommandItem key={r.id} value={'guess ' + r.name} onSelect={() => pick('student', r.name)}><Face s={r} size="size-6" />{r.name}<Check className="ml-auto opacity-40" /></CommandItem>
                ))}
              </CommandGroup>
            )}
            <CommandGroup heading="Not a student">
              <CommandItem value="professor" onSelect={() => pick('professor', null)}><GraduationCap />The professor</CommandItem>
              <CommandItem value="not a student music video noise ta" onSelect={() => pick('not_student', null)}><Ban />Not a student (music, video, TA, noise)</CommandItem>
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup heading="Students">
              {roster.map((r) => (
                <CommandItem key={r.id} value={r.name} onSelect={() => pick('student', r.name)}><Face s={r} size="size-6" />{r.name}</CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
