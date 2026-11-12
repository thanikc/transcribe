export type MeetingStatus = "recording" | "transcribing" | "transcribed" | "failed";
export type CaptureMode = "mic" | "mic+system" | "file";
export type LanguageCode = "auto" | "th" | "en";

export interface TranscriptionProgress {
  step: string;
  step_number: number;
  steps: number;
  fraction: number | null;
  elapsed: number;
}

export interface Meeting {
  id: string;
  title: string;
  started_at: string;
  duration: number | null;
  mode: CaptureMode | string;
  language: LanguageCode | string;
  model?: string | null;
  status: MeetingStatus;
  tracks: string[];
  audio_bytes: number;
  progress: TranscriptionProgress | null;
  speaker_names?: Record<string, string>;
  detected_languages?: Record<string, string>;
  warnings?: string[];
  error?: string | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string | null;
}

export interface MeetingDetail {
  meeting: Meeting;
  notes: string | null;
  segments: TranscriptSegment[] | null;
  transcript: string | null;
}

export interface RecorderStatus {
  recording: boolean;
  meeting_id?: string;
  title?: string;
  elapsed?: number;
  levels?: Record<string, number>;
}

export interface SpeechModelInfo {
  name: string;
  downloaded: boolean;
  default: boolean;
  size?: string;
}

export interface AudioDeviceInfo {
  id: string;
  name: string;
  default?: boolean;
}

export interface TrackSourceConfig {
  chosen: AudioDeviceInfo | null;
  devices: AudioDeviceInfo[];
}

export type SourcesMap = Record<string, TrackSourceConfig>;

export interface SearchHit {
  meeting_id: string;
  title: string;
  start: number;
  timestamp: string;
  speaker?: string | null;
  text: string;
}

export interface VersionState {
  version: string;
  update: string | null;
  checked?: boolean;
  error?: string | null;
  can_install?: boolean;
}
