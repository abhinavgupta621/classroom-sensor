import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Pause, Play, Video, X, Gauge } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Slider } from '@/components/ui/slider';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { day } from './types';
import { audioUrl, videoSource, HOSTED, PUBLIC } from './hosted';

/* One audio element for the whole portal. A clip plays a span of a class's audio and stops at
   its end; "class" mode keeps going so the transcript can follow along. */

export type Clip = { date: string; start: number; end?: number; title: string; sub?: string; mode?: 'clip' | 'class' };
type Ctx = {
  clip: Clip | null; playing: boolean; time: number;
  play: (c: Clip) => void; toggle: () => void; isCurrent: (date: string, start: number) => boolean;
};
const PlayerCtx = createContext<Ctx | null>(null);
export const usePlayer = () => useContext(PlayerCtx)!;

const clock = (s: number) => `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audio = useRef<HTMLAudioElement>(null);
  const [clip, setClip] = useState<Clip | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [rate, setRate] = useState(1);
  const [video, setVideo] = useState(false);

  const play = useCallback((c: Clip) => {
    if (PUBLIC) return;
    const a = audio.current!;
    const src = audioUrl(c.date);
    setClip(c);
    const go = () => { a.currentTime = Math.max(0, c.start - 0.3); a.play().catch(() => {}); };
    if (!a.src.endsWith(src)) { a.src = src; a.addEventListener('loadedmetadata', go, { once: true }); a.load(); } else go();
  }, []);
  const toggle = useCallback(() => { const a = audio.current!; if (a.paused) a.play().catch(() => {}); else a.pause(); }, []);
  const isCurrent = useCallback((date: string, start: number) => !!clip && clip.date === date && Math.abs(clip.start - start) < 0.01, [clip]);

  useEffect(() => { if (audio.current) audio.current.playbackRate = rate; }, [rate, clip]);
  useEffect(() => {
    const a = audio.current!;
    const tick = () => {
      setTime(a.currentTime);
      if (clip?.mode !== 'class' && clip?.end != null && a.currentTime >= clip.end + 0.3) a.pause();
    };
    const on = () => setPlaying(true), off = () => setPlaying(false);
    a.addEventListener('timeupdate', tick); a.addEventListener('play', on); a.addEventListener('pause', off);
    return () => { a.removeEventListener('timeupdate', tick); a.removeEventListener('play', on); a.removeEventListener('pause', off); };
  }, [clip]);

  const span = clip?.mode === 'class' || clip?.end == null ? null : [clip.start, clip.end] as const;
  const pos = span ? Math.min(100, Math.max(0, ((time - span[0]) / Math.max(0.1, span[1] - span[0])) * 100)) : 0;

  return (
    <PlayerCtx.Provider value={{ clip, playing, time, play, toggle, isCurrent }}>
      {children}
      <audio ref={audio} preload="none" />
      {clip && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5">
            <Button size="icon" className="size-10 shrink-0 rounded-full" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'}>
              {playing ? <Pause /> : <Play className="translate-x-px" />}
            </Button>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{clip.title}</div>
              <div className="truncate text-xs text-muted-foreground">{day(clip.date)} · {clock(time)}{clip.sub ? ` · ${clip.sub}` : ''}</div>
              {span && <Slider className="mt-1.5" value={[pos]} max={100} step={0.1}
                onValueChange={([v]) => { const a = audio.current!; a.currentTime = span[0] + (v / 100) * (span[1] - span[0]); }} />}
            </div>
            <Tooltip><TooltipTrigger asChild>
              <Button variant="ghost" size="sm" onClick={() => setRate(rate === 1 ? 1.5 : rate === 1.5 ? 2 : 1)} className="tabular-nums"><Gauge />{rate}×</Button>
            </TooltipTrigger><TooltipContent>Playback speed</TooltipContent></Tooltip>
            {clip.end != null && (
              <Button variant="outline" size="sm" onClick={() => { audio.current?.pause(); setVideo(true); }}><Video /> Watch</Button>
            )}
            <Button variant="ghost" size="icon" onClick={() => { audio.current?.pause(); setClip(null); }} aria-label="Close player"><X /></Button>
          </div>
        </div>
      )}
      <Dialog open={video} onOpenChange={setVideo}>
        <DialogContent className="max-w-[95vw] sm:max-w-4xl">
          <DialogTitle>{clip?.title}</DialogTitle>
          <DialogDescription>Room camera during this moment, {clip && day(clip.date)} {clip && clock(clip.start)}. {HOSTED ? 'Small copy of the camera; the original is on the pilot machine.' : 'The clip is cut on the fly; it can take a few seconds to start.'}</DialogDescription>
          {video && clip && clip.end != null && (
            <ClipVideo date={clip.date} start={clip.start} end={clip.end} />
          )}
        </DialogContent>
      </Dialog>
    </PlayerCtx.Provider>
  );
}

export function PlayButton({ clip, size = 'icon', label, className }: { clip: Clip; size?: 'icon' | 'sm'; label?: string; className?: string }) {
  const p = usePlayer();
  const on = p.isCurrent(clip.date, clip.start) && p.playing;
  if (PUBLIC) return null;
  return (
    <Button variant={on ? 'default' : 'outline'} size={size === 'icon' && !label ? 'icon' : 'sm'}
      className={cn(size === 'icon' && !label && 'size-7 rounded-full', className)}
      onClick={(e) => { e.stopPropagation(); if (p.isCurrent(clip.date, clip.start)) p.toggle(); else p.play(clip); }}
      aria-label={on ? 'Pause' : `Play ${clip.title}`}>
      {on ? <Pause /> : <Play className="translate-x-px" />}{label}
    </Button>
  );
}

function ClipVideo({ date, start, end }: { date: string; start: number; end: number }) {
  const { src, from, to } = videoSource(date, start, end);
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current; if (!v || !from) return;
    const seek = () => { v.currentTime = from; v.play().catch(() => {}); };
    if (v.readyState >= 1) seek(); else v.addEventListener('loadedmetadata', seek, { once: true });
  }, [src, from]);
  return <video ref={ref} src={src} controls autoPlay={!from} playsInline className="w-full rounded-md bg-black"
    onTimeUpdate={(e) => { if (to != null && e.currentTarget.currentTime >= to) e.currentTarget.pause(); }} />;
}
