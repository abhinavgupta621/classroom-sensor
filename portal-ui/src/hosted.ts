/** The hosted copy (built with VITE_HOSTED=1) is read-only: data, audio and video are static
    files, and labelling stays in the local portal, which can re-match voices. */
export const HOSTED = (import.meta as unknown as { env: Record<string, string | undefined> }).env.VITE_HOSTED === '1';
/** The public copy (VITE_PUBLIC=1, also hosted) has pseudonyms, blurred faces, no audio and no transcript text. */
export const PUBLIC = (import.meta as unknown as { env: Record<string, string | undefined> }).env.VITE_PUBLIC === '1';
export const dataUrl = HOSTED ? '/portal.json' : '/api/portal';
export const audioUrl = (date: string) => (HOSTED ? `/audio/${date}.m4a` : `/api/audio/${date}`);
/** Hosted video is cut into 15-minute files; returns the file and where to start in it. */
export const CHUNK_S = 900;
export function videoSource(date: string, start: number, end: number) {
  if (!HOSTED) return { src: `/api/clip/${date}?start=${start}&end=${end}`, from: 0, to: undefined as number | undefined };
  const n = Math.floor(Math.max(0, start - 1) / CHUNK_S);
  return { src: `/video/${date}/${n}.mp4`, from: Math.max(0, start - 1 - n * CHUNK_S), to: Math.min(CHUNK_S, end + 1 - n * CHUNK_S) };
}
