export type Seen = { seconds: number; present: boolean; first?: string; last?: string; score?: number; tile: string | null };
export type Score = { relevance: number; evidence: number; builds_on_others: number; insight: number; mean: number };

export type Student = {
  id: string; name: string; photo: string; team?: string | null;
  attendance: Record<string, Seen>;
  sessions_present: number; seconds_total: number;
  comments: number; comments_to_check: number; talk_seconds: number; called: number; voiceprint: boolean; avg_score: number | null;
};

export type Room = { preset: number; faces: number; at: string; in_panorama: boolean; image: string };
export type Call = { t: number; at: string; student: string; student_id: string; text: string };

export type Session = {
  date: string; id: string; resolution?: string; median_face_px?: number;
  seconds_students_on_screen?: number; named_any?: number; wrong_section_people?: number; present_3s: number;
  professor_minutes: number; student_minutes: number; duration: number; class_start: number; camera: [number, number][]; calls: Call[]; rooms: Room[]; panorama: string | null;
};

export type Comment = {
  date: string; at: string; start: number; end: number; seconds: number; student: string; student_id: string;
  how: 'called by name' | 'voice match' | 'you labelled'; confidence: number | null; text: string; score: Score | null; seen_that_day: boolean;
};

export type Row = {
  start: number; end: number; at: string; role: 'professor' | 'student' | 'short' | 'preclass'; text: string;
  speaker: string | null; how: string | null; confidence: number | null; score: Score | null;
};

export type VoiceClip = { date: string; start: number; end: number; text: string; at?: string };
export type Voices = {
  learned: { student: string; student_id: string; anchors: number; manual: number; matches: number; samples: VoiceClip[] }[];
  unknown: { id: number; turns: number; seconds: number; spans: { date: string; start: number; end: number }[]; classes: number; suggestion: { student: string; student_id: string; similarity: number } | null; clips: VoiceClip[] }[];
  unknown_total: number; labels: number;
};

export type Portal = {
  section: string; course: string; professor: string; generated: string;
  roster: Student[]; sessions: Session[]; comments: Comment[]; transcripts: Record<string, Row[]>; voices: Voices;
};

export const day = (d: string) =>
  new Date(d + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
export const mins = (s: number) => (s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`);
export const initials = (n: string) => n.split(' ').map((p) => p[0]).slice(0, 2).join('');
