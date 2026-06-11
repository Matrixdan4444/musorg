export type IssueSeverity = "danger" | "warning" | "success" | "neutral";
export type LanguageCode = "en" | "ru";
export type ThemeMode = "light" | "dark";
export type AccentColor = "violet" | "indigo" | "blue" | "teal" | "sky" | "emerald" | "amber" | "rose";
export type AlbumCompilationOverride = "auto" | "true" | "false";
export type AlbumExplicitOverride = "auto" | "true" | "false";
export type CapitalizationMode = "none" | "title_case" | "sentence_case" | "upper" | "lower";
export type MetadataProviderOverride = "auto" | "deezer" | "musicbrainz";
export type YearSourceOverride = "auto" | "local_tags" | "deezer" | "musicbrainz";
export type CoverHandlingMode = "auto" | "keep_existing" | "force_deezer" | "force_musicbrainz" | "remove";
export type WorkspaceSourceMode = "input" | "output";
export type RuntimeSessionState = "NO_ACTIVE_RUN" | "RUN_START" | "RUN_PROGRESS" | "RUN_COMPLETE" | "RUN_CLEARED";
export type AlbumFolderPreset = "artist_year_album" | "artist_album_year" | "artist_album" | "genre_artist_album" | "custom";
export type DiscHandlingMode = "keep_together" | "flatten" | "prefix_disc";
export type FileNamingMode = "track_title" | "artist_title" | "track_artist_title" | "title_only";
export type SeparatorStyle = "hyphen" | "dot" | "space" | "minimal";
export type DuplicateHandlingMode = "keep_everything" | "prefer_best_version" | "move_duplicates_to_archive";
export type FilenameCompatibilityMode = "preserve_original" | "cross_platform_safe";
export type OutputFormatToken = "artist" | "album" | "year" | "genre" | "disc" | "track_number" | "title" | "folder_break";

export interface MetadataPreservationCoreSettings {
  trackTitle: boolean;
  trackArtist: boolean;
  albumTitle: boolean;
  albumArtist: boolean;
  trackNumber: boolean;
  discNumber: boolean;
  discTotal: boolean;
}

export interface MetadataPreservationReleaseSettings {
  releaseDate: boolean;
  genre: boolean;
  releaseType: boolean;
  explicit: boolean;
  compilation: boolean;
}

export interface MetadataPreservationArtworkSettings {
  embedArtwork: boolean;
  saveCoverJpg: boolean;
  replaceLowQualityArtwork: boolean;
  preserveHigherQualityArtwork: boolean;
}

export interface MetadataPreservationLibrarySettings {
  replayGain: boolean;
  singleOriginalTrackNumber: boolean;
}

export interface MetadataPreservationAdvancedIdsSettings {
  musicBrainzReleaseId: boolean;
  musicBrainzTrackId: boolean;
}

export interface MetadataPreservationSettings {
  core: MetadataPreservationCoreSettings;
  release: MetadataPreservationReleaseSettings;
  artwork: MetadataPreservationArtworkSettings;
  library: MetadataPreservationLibrarySettings;
  advancedIds: MetadataPreservationAdvancedIdsSettings;
}

export interface AlbumIssue {
  id: string;
  label: string;
  severity: Exclude<IssueSeverity, "neutral">;
}

export interface MetadataDiffField {
  id: string;
  label: string;
  before: string;
  after: string;
  origin: "auto_fix" | "manual_override";
}

export interface CleanupAction {
  kind: string;
  label: string;
  source: string;
  origin: "auto_fix" | "manual_override";
}

export interface ProviderRejection {
  provider: string;
  reason: string;
  message: string;
}

export interface ProviderDecision {
  metadataProvider?: string | null;
  artworkProvider?: string | null;
  winner?: string | null;
  path?: string | null;
  rejectedProviders: ProviderRejection[];
}

export interface MatchReason {
  provider: string;
  status: string;
  message: string;
}

export interface ConfidenceSignal {
  id: string;
  label: string;
  status: "accepted" | "warning" | "rejected" | "info";
  scoreImpact: number;
  message: string;
}

export interface ConfidenceSummary {
  level: "high" | "medium" | "low" | "suspicious";
  score: number;
  label: string;
  reasons: string[];
  signals: ConfidenceSignal[];
}

export interface SuspiciousMetadataItem {
  id: string;
  label: string;
  severity: Exclude<IssueSeverity, "neutral">;
  message: string;
  details?: Record<string, unknown>;
}

export interface MetadataIntelligence {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  diff: MetadataDiffField[];
  cleanupActions: CleanupAction[];
  providerDecisions: ProviderDecision;
  matchReasoning: MatchReason[];
  confidence: ConfidenceSummary;
  suspiciousMetadata: SuspiciousMetadataItem[];
}

export interface ReleaseAction {
  id: string;
  label: string;
  reason: string;
  tone: "success" | "warning" | "danger" | "info";
}

export interface ReleaseIntelligence {
  releaseFamilyId?: string | null;
  releaseVariantId?: string | null;
  releaseVariantType: "original" | "remaster" | "deluxe" | "anniversary" | "expanded" | "compilation" | "live" | "bootleg" | "japanese_edition" | "vinyl_rip" | "web_release" | "cd_rip" | "alternate_release" | "unknown";
  relationshipStatus: "best_version" | "exact_duplicate" | "near_duplicate" | "better_version_available" | "related_release" | "possible_related_release" | "suspicious_release" | "standalone";
  qualityScore: number;
  qualityRank?: number | null;
  duplicateConfidence: number;
  relatedReleaseCount: number;
  bestVersion: boolean;
  fakeFlacStatus: "none" | "possible" | "likely" | "suspicious";
  formatSummary?: string | null;
  reasons: string[];
  releaseActions: ReleaseAction[];
}

export type SmartActionType = "keep_recommended" | "archive_recommended" | "replace_recommended" | "cleanup_needed" | "processing_needed" | "review_needed";
export type SmartActionGroup = "album" | "family" | "collection";
export type SmartActionConfidenceBand = "low" | "medium" | "high" | "very_high";
export type SmartActionCapability = "auto_fixable" | "semi_auto_fixable" | "manual_review_required" | "informational_only";
export type SmartActionResolutionConfidence = "low" | "medium" | "high";
export type SmartActionTier = "automatic_fix_available" | "fix_prepared" | "review_needed" | "informational";
export type SmartActionExecutionMode = "auto_apply_in_cleanup" | "staged_confirmation" | "manual_only" | "none";
export type SmartActionFixMethod = "global_cleanup" | "manual_review" | "external_only";
export type SmartActionCtaIntent = "run_cleanup" | "none";
export type SmartActionAutoFixStatus = "auto_fix_pending" | "auto_fix_attempted" | "auto_fix_blocked" | "auto_fix_failed" | "not_auto_fixable";
export type SmartActionSkipReason =
  | "provider_conflict"
  | "confidence_too_low"
  | "track_mapping_ambiguous"
  | "release_structure_mismatch"
  | "unsafe_metadata_overwrite"
  | "provider_data_unavailable"
  | "unsupported_fix_path";
export type SmartActionCategory = "metadata" | "artwork" | "sequencing" | "duplicate" | "release_quality" | "suspicious_audio" | "collection_cleanup" | "processing";
export type SmartActionImpact = "cosmetic" | "moderate" | "important";
export interface PreparedFix {
  kind: string;
  summary: string;
  sourceAlbumIds: string[];
  targetAlbumIds: string[];
  plannedChanges?: string[];
}

export interface SmartAction {
  id: string;
  type: SmartActionType;
  group: SmartActionGroup;
  severity: IssueSeverity;
  category: SmartActionCategory;
  impact: SmartActionImpact;
  title: string;
  message: string;
  reasoning: string[];
  sourceSignals: string[];
  detectedBy: string[];
  tier: SmartActionTier;
  executionMode: SmartActionExecutionMode;
  primaryEligible: boolean;
  autoFixReason?: string | null;
  preparedFix?: PreparedFix | null;
  canMusorgFix: boolean;
  fixMethod: SmartActionFixMethod;
  ctaLabel?: string | null;
  ctaIntent: SmartActionCtaIntent;
  afterAction?: string | null;
  blockingReason?: string | null;
  autoFixStatus: SmartActionAutoFixStatus;
  autoFixSupported: boolean;
  autoFixAttempted: boolean;
  autoFixExplanation: string;
  skipReason?: SmartActionSkipReason | null;
  blockingSignals: string[];
  capability: SmartActionCapability;
  whyMatters: string;
  suggestedFix: string;
  evidence: string[];
  resolutionConfidence: SmartActionResolutionConfidence;
  confidence: number;
  confidenceBand: SmartActionConfidenceBand;
  affectedAlbumIds: string[];
  actionable: boolean;
  destructive: boolean;
  recommended: boolean;
  reversible: boolean;
  priority: number;
  snapshotId: string;
  generatedFromSnapshotId: string;
  generatedAt?: string | null;
  contextSummary?: string | null;
  dismissible: boolean;
  snoozable: boolean;
  persistent: boolean;
  suppressedByActionId?: string | null;
  suppressedReason?: string | null;
  supersededByActionId?: string | null;
}

export interface IssueCounts {
  danger: number;
  warning: number;
  success: number;
}

export interface AlbumListItem {
  id: string;
  title: string;
  artist: string;
  year: string;
  trackCount: number;
  coverUrl: string;
  selected?: boolean;
  dirty?: boolean;
  processingState?: string | null;
  outputPath?: string | null;
  provider?: string | null;
  releaseType?: string | null;
  confidenceLevel?: "high" | "medium" | "low" | "suspicious" | null;
  lowConfidence?: boolean;
  metadataIntelligence?: MetadataIntelligence | null;
  releaseIntelligence?: ReleaseIntelligence | null;
  topAction?: SmartAction | null;
  actionSummary?: SmartAction[];
  actionCount?: number;
  issueCounts: IssueCounts;
  status: "ready" | "issues";
}

export interface TrackRow {
  id: string;
  checked: boolean;
  index: number;
  title: string;
  artist: string;
  duration: string;
  issues: AlbumIssue[];
}

export interface InspectorMetric {
  id: string;
  label: string;
  value: string;
  severity: IssueSeverity;
}

export interface AlbumInspectorData {
  id: string;
  coverUrl: string;
  title: string;
  artist: string;
  year: string;
  albumArtist: string;
  genre: string;
  disc: string;
  metrics: InspectorMetric[];
  issues: AlbumIssue[];
  processingState?: string | null;
  outputPath?: string | null;
  provider?: string | null;
  confidenceLevel?: "high" | "medium" | "low" | "suspicious" | null;
  lowConfidence?: boolean;
  metadataIntelligence?: MetadataIntelligence | null;
  releaseIntelligence?: ReleaseIntelligence | null;
  topAction?: SmartAction | null;
  actionSummary?: SmartAction[];
  actionCount?: number;
}

export interface RelatedReleaseItem {
  id: string;
  releaseFamilyId?: string | null;
  releaseVariantId?: string | null;
  title: string;
  artist: string;
  year: string;
  trackCount: number;
  formatSummary: string;
  qualityScore: number;
  qualityRank?: number | null;
  bestVersion: boolean;
  releaseVariantType: string;
  relationshipStatus: string;
  duplicateConfidence: number;
  fakeFlacStatus: "none" | "possible" | "likely" | "suspicious";
  reasons: string[];
  releaseActions: ReleaseAction[];
  current: boolean;
}

export interface ReleaseComparisonPayload {
  albumId: string;
  releaseFamilyId?: string | null;
  current: RelatedReleaseItem;
  family: RelatedReleaseItem[];
  possibleMatches: RelatedReleaseItem[];
}

export interface LogStep {
  id: string;
  title: string;
  status: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  severity: "info" | "warning" | "error" | "success";
  source: string;
  channel?: "activity" | "runtime" | "diagnostic" | string;
  type: string;
  stage?: string | null;
  message: string;
  payload?: Record<string, unknown> | null;
  albumId?: string | null;
  runId?: string | null;
  sequence?: number | null;
}

export interface SummaryStat {
  id: string;
  label: string;
  value: string;
  hint: string;
  severity: IssueSeverity;
}

export interface ImportWorkspaceData {
  libraryPath: string;
  albums: AlbumListItem[];
  selectedAlbumId: string;
  inspector: AlbumInspectorData;
  tracks: TrackRow[];
  logs: LogEntry[];
  logSteps: LogStep[];
  summary: SummaryStat[];
}

export interface AlbumsPayload {
  libraryPath: string;
  albums: AlbumListItem[];
}

export interface AlbumDetailPayload {
  album: AlbumInspectorData;
}

export interface TracksPayload {
  tracks: TrackRow[];
}

export interface ReleaseComparisonApiPayload {
  albumId: string;
  releaseFamilyId?: string | null;
  current: RelatedReleaseItem;
  family: RelatedReleaseItem[];
  possibleMatches: RelatedReleaseItem[];
}

export interface AlbumActionsPayload {
  albumId: string;
  snapshotId: string;
  topAction?: SmartAction | null;
  actionSummary: SmartAction[];
  actionCount: number;
  recommendationSummary?: string | null;
  albumActions: SmartAction[];
  familyActions: SmartAction[];
  suppressedActions: SmartAction[];
}

export interface LogsPayload {
  activeRunId: string | null;
  sessionState: RuntimeSessionState;
  steps: LogStep[];
  logs: LogEntry[];
}

export interface HealthPayload {
  status: "ok";
  library_path: string;
}

export interface AppearanceSettings {
  themeMode: ThemeMode;
  accentColor: AccentColor;
}

export interface LibrarySettingsPayload {
  libraryRoot: string;
  outputRoot: string;
  developerMode: boolean;
  language: LanguageCode;
  themeMode: ThemeMode;
  accentColor: AccentColor;
  duplicateHandling: DuplicateHandlingMode;
  filenameCompatibility: FilenameCompatibilityMode;
  outputFormat: OutputFormatSettings;
  metadataPreservation: MetadataPreservationSettings;
  isConfigured: boolean;
  isAvailable: boolean;
  source: "settings" | "environment" | "none";
  pickerAvailable: boolean;
  message?: string | null;
  error?: string | null;
}

export interface UpdateLibrarySettingsPayload {
  libraryRoot: string;
  outputRoot: string;
  developerMode: boolean;
  language: LanguageCode;
  themeMode: ThemeMode;
  accentColor: AccentColor;
  duplicateHandling: DuplicateHandlingMode;
  filenameCompatibility: FilenameCompatibilityMode;
  outputFormat: OutputFormatSettings;
  metadataPreservation: MetadataPreservationSettings;
}

export interface OutputFormatSettings {
  albumFolderPreset: AlbumFolderPreset;
  discHandling: DiscHandlingMode;
  fileNaming: FileNamingMode;
  separatorStyle: SeparatorStyle;
  customAlbumPattern: OutputFormatToken[];
  customAdvancedTemplate?: string | null;
}

export interface LibraryPickerPayload {
  libraryRoot: string | null;
  canceled: boolean;
  pickerAvailable: boolean;
  error?: string | null;
}

export interface ClearCachePayload {
  cleared: boolean;
  metadataEntriesCleared: number;
  processingStateCleared: boolean;
}

export interface AlbumMetadataOverride {
  albumId: string;
  albumTitle?: string;
  albumArtist?: string;
  genre?: string;
  year?: string;
  disc?: string;
  discTotal?: string;
  compilation?: AlbumCompilationOverride;
  explicit?: AlbumExplicitOverride;
  capitalizationMode?: CapitalizationMode;
  normalizeFeaturingArtists?: boolean;
  overwriteExistingTags?: boolean;
  metadataProvider?: MetadataProviderOverride;
  yearSource?: YearSourceOverride;
  coverHandlingMode?: CoverHandlingMode;
}

export interface CleanLibraryRequestPayload {
  overrides: AlbumMetadataOverride[];
}

export interface CleanLibraryPayload {
  runId: string;
  status: string;
  libraryRoot: string;
  outputPath: string | null;
  albumsProcessed: number;
  tracksProcessed: number;
  summaryPath?: string | null;
}

export interface BatchEditAlbumDraft {
  albumTitle: string;
  albumArtist: string;
  releaseArtist: string;
  year: string;
  genre: string;
  releaseType: string;
  label: string;
  catalogNumber: string;
  copyright: string;
  comment: string;
}

export interface BatchEditTrackRow {
  id: string;
  path?: string | null;
  index: number;
  title: string;
  artist: string;
  albumArtist: string;
  discNumber: string;
  trackNumber: string;
  genre: string;
  comment: string;
  duration: string;
  issues: AlbumIssue[];
}

export interface BatchEditArtworkState {
  hasArtwork: boolean;
  coverUrl: string;
  source?: string | null;
}

export interface BatchEditArtworkDraft {
  mode: "keep" | "upload" | "fetch_provider" | "remove";
  coverUrl?: string | null;
  imageBase64?: string | null;
  mimeType?: string | null;
  filename?: string | null;
}

export interface BatchEditEditorState {
  album: BatchEditAlbumDraft;
  tracks: BatchEditTrackRow[];
  artwork: BatchEditArtworkState;
}

export interface BatchEditCandidate {
  id: string;
  provider: "deezer" | "musicbrainz";
  providerReleaseId: string;
  title: string;
  artist: string;
  year: string;
  trackCount: number;
  coverUrl: string;
  releaseType: string;
  artworkWidth?: number | null;
  artworkHeight?: number | null;
}

export interface BatchEditFindReleasePayload {
  albumId: string;
  queryArtist: string;
  queryAlbum: string;
  candidates: BatchEditCandidate[];
}

export interface BatchEditArtworkOption {
  id: string;
  provider: "deezer" | "musicbrainz";
  coverUrl: string;
  width?: number | null;
  height?: number | null;
  releaseTitle?: string | null;
}

export interface BatchEditFindArtworkPayload {
  albumId: string;
  queryArtist: string;
  queryAlbum: string;
  options: BatchEditArtworkOption[];
}

export interface BatchEditApplyReleasePayload {
  albumId: string;
  candidate: BatchEditCandidate;
  album: BatchEditAlbumDraft;
  tracks: BatchEditTrackRow[];
  artwork: BatchEditArtworkDraft;
  diff: MetadataDiffField[];
}

export interface BatchEditAlbumDetailPayload {
  album: AlbumInspectorData;
  relatedReleases: ReleaseComparisonPayload;
  actions: AlbumActionsPayload;
  editor: BatchEditEditorState;
}

export interface BatchEditSaveRequestPayload {
  album: BatchEditAlbumDraft;
  tracks: BatchEditTrackRow[];
  artwork: BatchEditArtworkDraft;
  releaseReplacement?: BatchEditApplyReleasePayload | null;
}

export interface BatchEditSavePayload {
  saved: boolean;
  albumId: string;
}

export interface BatchEditBulkUpdateRequestPayload {
  albumIds: string[];
  albumArtist?: string | null;
  year?: string | null;
  genre?: string | null;
  releaseType?: string | null;
  comment?: string | null;
}

export interface BatchEditBulkUpdatePayload {
  saved: boolean;
  albumIds: string[];
}
