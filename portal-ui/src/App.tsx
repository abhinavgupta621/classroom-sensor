import { dataUrl, PUBLIC } from './hosted';
import { useCallback, useEffect, useState } from 'react';
import { AudioLines, BookOpenText, CalendarDays, Moon, Search, Sun, Users, type LucideIcon } from 'lucide-react';
import { Toaster } from '@/components/ui/sonner';
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { TooltipProvider } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { Portal, Student } from './types';
import { day } from './types';
import { Face } from './bits';
import { PlayerProvider } from './player';
import Sessions from './pages/Sessions';
import People from './pages/People';
import Voices from './pages/Voices';
import Method from './pages/Method';
import StudentSheet from './StudentSheet';

const PLACES: { id: string; label: string; icon: LucideIcon; hint: string }[] = [
  { id: 'sessions', label: 'Sessions', icon: CalendarDays, hint: 'One class at a time' },
  { id: 'people', label: 'People', icon: Users, hint: 'Every student across classes' },
  { id: 'voices', label: 'Voices', icon: AudioLines, hint: 'Name unknown voices' },
  { id: 'method', label: 'Method', icon: BookOpenText, hint: 'How it works and how well' },
];

export default function App() {
  const [data, setData] = useState<Portal | null>(null);
  const [err, setErr] = useState('');
  const [place, setPlace] = useState(() => { const h = location.hash.slice(1).split('?')[0]; return PLACES.some((p) => p.id === h) ? h : 'sessions'; });
  const [openId, setOpenId] = useState<string | null>(null);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  const [search, setSearch] = useState(false);

  const reload = useCallback(async () => {
    const r = await fetch(dataUrl, { cache: 'no-store' });
    if (!r.ok) throw new Error(r.statusText);
    setData(await r.json());
  }, []);
  useEffect(() => { reload().catch((e) => setErr(String(e))); }, [reload]);
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); try { localStorage.setItem('theme', dark ? 'dark' : 'light'); } catch { /* private mode */ } }, [dark]);
  useEffect(() => { if (location.hash.slice(1).split('?')[0] !== place) history.replaceState(null, '', '#' + place); window.scrollTo({ top: 0 }); }, [place]);
  useEffect(() => {
    const on = () => { const h = location.hash.slice(1).split('?')[0]; if (PLACES.some((p) => p.id === h)) setPlace(h); };
    const key = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setSearch((v) => !v); } };
    addEventListener('hashchange', on); addEventListener('keydown', key);
    return () => { removeEventListener('hashchange', on); removeEventListener('keydown', key); };
  }, []);

  if (err) return <div className="p-8 text-bad">Couldn’t load the portal data: {err}. Run analysis/build_portal_data.py, then reload.</div>;
  if (!data) return <div className="p-8 text-sm text-muted-foreground">Loading…</div>;
  const open = openId ? data.roster.find((r) => r.id === openId) ?? null : null;
  const openStudent = (s: Student) => setOpenId(s.id);

  return (
    <TooltipProvider delayDuration={150}>
      <PlayerProvider>
        <div className="flex min-h-screen">
          {/* Sidebar, as on berkeleyhaas.me */}
          <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-surface/50 p-3 md:flex">
            <div className="flex items-center gap-2 px-2 py-2">
              <span className="flex size-7 items-center justify-center rounded-lg bg-oski text-xs font-bold text-white">{PUBLIC ? 'A' : '205'}</span>
              <div className="min-w-0 leading-tight">
                <div className="truncate text-sm font-semibold">Classroom research</div>
                <div className="truncate text-xxs text-muted-foreground">{PUBLIC ? data.course : `Leading People · ${data.section}`}</div>
              </div>
            </div>
            <button onClick={() => setSearch(true)} className="mt-3 flex h-8 items-center gap-2 rounded-lg border border-line bg-raised px-2.5 text-sm text-muted-foreground hover:border-line-strong">
              <Search className="size-3.5" />Find a student<kbd className="ml-auto text-xxs">⌘K</kbd>
            </button>
            <nav className="mt-4 space-y-0.5">
              {PLACES.map((p) => (
                <button key={p.id} onClick={() => setPlace(p.id)} title={p.hint}
                  className={cn('flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors',
                    place === p.id ? 'bg-accent-tint font-semibold text-foreground' : 'text-muted-foreground hover:bg-surface hover:text-foreground')}>
                  <p.icon className="size-4" strokeWidth={place === p.id ? 2.2 : 1.9} />{p.label}
                  {p.id === 'voices' && data.voices.unknown_total > 0 && <span className="ml-auto rounded-full bg-warn-tint px-1.5 text-xxs font-semibold text-warn">{data.voices.unknown_total}</span>}
                </button>
              ))}
            </nav>
            <div className="mt-auto space-y-2 px-2 text-xxs text-muted-foreground">
              <div>{PUBLIC ? 'One instructor' : `Prof. ${data.professor}`} · {data.roster.length} students · {data.sessions.length} classes, {day(data.sessions[0].date)} – {day(data.sessions.at(-1)!.date)}</div>
              <div>{PUBLIC ? 'Public edition: every name is a pseudonym, faces are blurred, and there is no audio or transcript text.' : 'Internal research pilot. Runs on this Mac only.'}</div>
              <button onClick={() => setDark(!dark)} className="flex items-center gap-1.5 hover:text-foreground">{dark ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}{dark ? 'Light' : 'Dark'}</button>
            </div>
          </aside>

          <div className="min-w-0 flex-1">
            {/* Phone: a top bar instead of the sidebar */}
            <div className="sticky top-0 z-20 flex items-center gap-1 overflow-x-auto border-b border-line bg-background/90 px-3 py-2 backdrop-blur md:hidden">
              {PLACES.map((p) => (
                <button key={p.id} onClick={() => setPlace(p.id)} className={cn('flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm', place === p.id ? 'bg-accent-tint font-semibold' : 'text-muted-foreground')}>
                  <p.icon className="size-4" />{p.label}
                </button>
              ))}
              <button onClick={() => setSearch(true)} className="ml-auto p-1.5" aria-label="Find a student"><Search className="size-4" /></button>
            </div>
            <main key={place} className="page-in mx-auto max-w-7xl px-4 pb-28 pt-6 md:px-8">
              {place === 'sessions' && <Sessions d={data} openStudent={openStudent} reload={reload} />}
              {place === 'people' && <People d={data} openStudent={openStudent} />}
              {place === 'voices' && <Voices d={data} openStudent={openStudent} reload={reload} />}
              {place === 'method' && <Method d={data} />}
            </main>
          </div>
        </div>
        <StudentSheet d={data} s={open} onClose={() => setOpenId(null)} reload={reload} />
        <CommandDialog open={search} onOpenChange={setSearch} title="Find" description="Jump to a student or a place">
          <CommandInput placeholder="Student name or place…" />
          <CommandList>
            <CommandEmpty>Nothing found.</CommandEmpty>
            <CommandGroup heading="Students">
              {data.roster.map((r) => (
                <CommandItem key={r.id} value={r.name} onSelect={() => { setSearch(false); setOpenId(r.id); }}>
                  <Face s={r} size="size-6" />{r.name}
                  <span className="ml-auto text-xxs text-muted-foreground">{r.sessions_present}/{data.sessions.length} classes · {r.comments} comments</span>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandGroup heading="Places">
              {PLACES.map((p) => <CommandItem key={p.id} value={'place ' + p.label} onSelect={() => { setSearch(false); setPlace(p.id); }}><p.icon />{p.label}</CommandItem>)}
            </CommandGroup>
          </CommandList>
        </CommandDialog>
        <Toaster position="top-center" />
      </PlayerProvider>
    </TooltipProvider>
  );
}
