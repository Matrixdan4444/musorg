from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IssueSeverity = Literal["danger", "warning", "success", "neutral"]
LanguageCode = Literal["en", "ru"]
ThemeMode = Literal["light", "dark"]
AccentColor = Literal["violet", "indigo", "blue", "teal", "sky", "emerald", "amber", "rose"]
DuplicateHandlingMode = Literal["keep_everything", "prefer_best_version", "move_duplicates_to_archive"]
FilenameCompatibilityMode = Literal["preserve_original", "cross_platform_safe"]


class OutputFormatSettingsSchema(BaseModel):
    albumFolderPreset: Literal["artist_year_album", "artist_album_year", "artist_album", "genre_artist_album", "custom"] = "artist_year_album"
    discHandling: Literal["keep_together", "flatten", "prefix_disc"] = "keep_together"
    fileNaming: Literal["track_title", "artist_title", "track_artist_title", "title_only"] = "track_title"
    separatorStyle: Literal["hyphen", "dot", "space", "minimal"] = "dot"
    customAlbumPattern: list[str] = Field(default_factory=lambda: ["artist", "folder_break", "year", "album"])
    customAdvancedTemplate: str | None = None


class MetadataPreservationCoreSchema(BaseModel):
    trackTitle: bool = True
    trackArtist: bool = True
    albumTitle: bool = True
    albumArtist: bool = True
    trackNumber: bool = True
    discNumber: bool = True
    discTotal: bool = True


class MetadataPreservationReleaseSchema(BaseModel):
    releaseDate: bool = True
    genre: bool = True
    releaseType: bool = True
    explicit: bool = True
    compilation: bool = True


class MetadataPreservationArtworkSchema(BaseModel):
    embedArtwork: bool = True
    saveCoverJpg: bool = False
    replaceLowQualityArtwork: bool = True
    preserveHigherQualityArtwork: bool = True


class MetadataPreservationLibrarySchema(BaseModel):
    replayGain: bool = True
    singleOriginalTrackNumber: bool = True


class MetadataPreservationAdvancedIdsSchema(BaseModel):
    musicBrainzReleaseId: bool = True
    musicBrainzTrackId: bool = True


class MetadataPreservationSettingsSchema(BaseModel):
    core: MetadataPreservationCoreSchema = Field(default_factory=MetadataPreservationCoreSchema)
    release: MetadataPreservationReleaseSchema = Field(default_factory=MetadataPreservationReleaseSchema)
    artwork: MetadataPreservationArtworkSchema = Field(default_factory=MetadataPreservationArtworkSchema)
    library: MetadataPreservationLibrarySchema = Field(default_factory=MetadataPreservationLibrarySchema)
    advancedIds: MetadataPreservationAdvancedIdsSchema = Field(default_factory=MetadataPreservationAdvancedIdsSchema)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    library_path: str


class LibrarySettingsResponse(BaseModel):
    libraryRoot: str
    outputRoot: str
    developerMode: bool = False
    language: LanguageCode = "en"
    themeMode: ThemeMode = "dark"
    accentColor: AccentColor = "violet"
    duplicateHandling: DuplicateHandlingMode = "keep_everything"
    filenameCompatibility: FilenameCompatibilityMode = "preserve_original"
    outputFormat: OutputFormatSettingsSchema = OutputFormatSettingsSchema()
    metadataPreservation: MetadataPreservationSettingsSchema = Field(default_factory=MetadataPreservationSettingsSchema)
    onboardingCompleted: bool = False
    onboardingDismissed: bool = False
    isConfigured: bool
    isAvailable: bool
    source: Literal["settings", "environment", "none"]
    pickerAvailable: bool
    message: str | None = None
    error: str | None = None


class UpdateLibrarySettingsRequest(BaseModel):
    libraryRoot: str
    outputRoot: str
    developerMode: bool = False
    language: LanguageCode = "en"
    themeMode: ThemeMode = "dark"
    accentColor: AccentColor = "violet"
    duplicateHandling: DuplicateHandlingMode = "keep_everything"
    filenameCompatibility: FilenameCompatibilityMode = "preserve_original"
    outputFormat: OutputFormatSettingsSchema = OutputFormatSettingsSchema()
    metadataPreservation: MetadataPreservationSettingsSchema = Field(default_factory=MetadataPreservationSettingsSchema)
    onboardingCompleted: bool | None = None
    onboardingDismissed: bool | None = None


class LibraryPickerResponse(BaseModel):
    libraryRoot: str | None
    canceled: bool
    pickerAvailable: bool
    error: str | None = None


class ClearCacheResponse(BaseModel):
    cleared: bool
    metadataEntriesCleared: int
    processingStateCleared: bool


class AlbumMetadataOverrideSchema(BaseModel):
    albumId: str
    albumTitle: str | None = None
    albumArtist: str | None = None
    genre: str | None = None
    year: str | None = None
    disc: str | None = None
    discTotal: str | None = None
    compilation: Literal["auto", "true", "false"] | None = None
    explicit: Literal["auto", "true", "false"] | None = None
    capitalizationMode: Literal["none", "title_case", "sentence_case", "upper", "lower"] | None = None
    normalizeFeaturingArtists: bool | None = None
    overwriteExistingTags: bool | None = None
    metadataProvider: Literal["auto", "deezer", "musicbrainz"] | None = None
    yearSource: Literal["auto", "local_tags", "deezer", "musicbrainz"] | None = None
    coverHandlingMode: Literal["auto", "keep_existing", "force_deezer", "force_musicbrainz", "remove"] | None = None


class CleanLibraryRequest(BaseModel):
    overrides: list[AlbumMetadataOverrideSchema] = []


class CleanLibraryResponse(BaseModel):
    runId: str
    status: str
    libraryRoot: str
    outputPath: str | None
    albumsProcessed: int
    tracksProcessed: int
    summaryPath: str | None = None


class BatchEditAlbumDraftSchema(BaseModel):
    albumTitle: str = ""
    albumArtist: str = ""
    releaseArtist: str = ""
    year: str = ""
    genre: str = ""
    releaseType: str = ""
    label: str = ""
    catalogNumber: str = ""
    copyright: str = ""
    comment: str = ""


class BatchEditTrackSchema(BaseModel):
    id: str
    path: str | None = None
    index: int
    title: str = ""
    artist: str = ""
    albumArtist: str = ""
    discNumber: str = ""
    trackNumber: str = ""
    genre: str = ""
    comment: str = ""
    duration: str = ""
    issues: list["AlbumIssueSchema"] = []


class BatchEditArtworkStateSchema(BaseModel):
    hasArtwork: bool = False
    coverUrl: str = ""
    source: str | None = None


class BatchEditEditorStateSchema(BaseModel):
    album: BatchEditAlbumDraftSchema
    tracks: list[BatchEditTrackSchema] = []
    artwork: BatchEditArtworkStateSchema = Field(default_factory=BatchEditArtworkStateSchema)


class BatchEditCandidateSchema(BaseModel):
    id: str
    provider: Literal["deezer", "musicbrainz"]
    providerReleaseId: str
    title: str
    artist: str
    year: str = "Unknown"
    trackCount: int = 0
    coverUrl: str = ""
    releaseType: str = ""
    artworkWidth: int | None = None
    artworkHeight: int | None = None


class BatchEditFindReleaseRequestSchema(BaseModel):
    artist: str | None = None
    album: str | None = None


class BatchEditFindReleaseResponseSchema(BaseModel):
    albumId: str
    queryArtist: str
    queryAlbum: str
    candidates: list[BatchEditCandidateSchema] = []


class BatchEditArtworkOptionSchema(BaseModel):
    id: str
    provider: Literal["deezer", "musicbrainz"]
    coverUrl: str
    width: int | None = None
    height: int | None = None
    releaseTitle: str | None = None


class BatchEditFindArtworkRequestSchema(BaseModel):
    artist: str | None = None
    album: str | None = None


class BatchEditFindArtworkResponseSchema(BaseModel):
    albumId: str
    queryArtist: str
    queryAlbum: str
    options: list[BatchEditArtworkOptionSchema] = []


class BatchEditApplyReleaseRequestSchema(BaseModel):
    provider: Literal["deezer", "musicbrainz"]
    providerReleaseId: str


class BatchEditArtworkDraftSchema(BaseModel):
    mode: Literal["keep", "upload", "fetch_provider", "remove"] = "keep"
    coverUrl: str | None = None
    imageBase64: str | None = None
    mimeType: str | None = None
    filename: str | None = None


class BatchEditApplyReleaseResponseSchema(BaseModel):
    albumId: str
    candidate: BatchEditCandidateSchema
    album: BatchEditAlbumDraftSchema
    tracks: list[BatchEditTrackSchema] = []
    artwork: BatchEditArtworkDraftSchema = Field(default_factory=BatchEditArtworkDraftSchema)
    diff: list["MetadataDiffFieldSchema"] = []


class BatchEditSaveRequestSchema(BaseModel):
    album: BatchEditAlbumDraftSchema = Field(default_factory=BatchEditAlbumDraftSchema)
    tracks: list[BatchEditTrackSchema] = []
    artwork: BatchEditArtworkDraftSchema = Field(default_factory=BatchEditArtworkDraftSchema)
    releaseReplacement: BatchEditApplyReleaseResponseSchema | None = None


class BatchEditSaveResponseSchema(BaseModel):
    saved: bool = True
    albumId: str


class BatchEditBulkUpdateRequestSchema(BaseModel):
    albumIds: list[str] = []
    albumArtist: str | None = None
    year: str | None = None
    genre: str | None = None
    releaseType: str | None = None
    comment: str | None = None


class BatchEditBulkUpdateResponseSchema(BaseModel):
    saved: bool = True
    albumIds: list[str] = []


class BatchEditAlbumDetailResponseSchema(BaseModel):
    album: "AlbumInspectorSchema"
    relatedReleases: "ReleaseComparisonResponseSchema"
    actions: "AlbumActionsResponseSchema"
    editor: BatchEditEditorStateSchema


class AlbumIssueSchema(BaseModel):
    id: str
    label: str
    severity: Literal["danger", "warning", "success"]


class MetadataDiffFieldSchema(BaseModel):
    id: str
    label: str
    before: str
    after: str
    origin: Literal["auto_fix", "manual_override"]


class CleanupActionSchema(BaseModel):
    kind: str
    label: str
    source: str
    origin: Literal["auto_fix", "manual_override"]


class ProviderRejectionSchema(BaseModel):
    provider: str
    reason: str
    message: str


class ProviderDecisionSchema(BaseModel):
    metadataProvider: str | None = None
    artworkProvider: str | None = None
    winner: str | None = None
    path: str | None = None
    rejectedProviders: list[ProviderRejectionSchema] = []


class MatchReasonSchema(BaseModel):
    provider: str
    status: str
    message: str


class ConfidenceSignalSchema(BaseModel):
    id: str
    label: str
    status: Literal["accepted", "warning", "rejected", "info"]
    scoreImpact: int
    message: str


class ConfidenceSummarySchema(BaseModel):
    level: Literal["high", "medium", "low", "suspicious"]
    score: int
    label: str
    reasons: list[str]
    signals: list[ConfidenceSignalSchema] = []


class SuspiciousMetadataItemSchema(BaseModel):
    id: str
    label: str
    severity: Literal["danger", "warning", "success"]
    message: str
    details: dict = {}


class MetadataIntelligenceSchema(BaseModel):
    before: dict
    after: dict
    diff: list[MetadataDiffFieldSchema]
    cleanupActions: list[CleanupActionSchema]
    providerDecisions: ProviderDecisionSchema
    matchReasoning: list[MatchReasonSchema]
    confidence: ConfidenceSummarySchema
    suspiciousMetadata: list[SuspiciousMetadataItemSchema]


class ReleaseActionSchema(BaseModel):
    id: str
    label: str
    reason: str
    tone: Literal["success", "warning", "danger", "info"]


class ReleaseIntelligenceSummarySchema(BaseModel):
    releaseFamilyId: str | None = None
    releaseVariantId: str | None = None
    releaseVariantType: Literal[
        "original",
        "remaster",
        "deluxe",
        "anniversary",
        "expanded",
        "compilation",
        "live",
        "bootleg",
        "japanese_edition",
        "vinyl_rip",
        "web_release",
        "cd_rip",
        "alternate_release",
        "unknown",
    ] = "unknown"
    relationshipStatus: Literal[
        "best_version",
        "exact_duplicate",
        "near_duplicate",
        "better_version_available",
        "related_release",
        "possible_related_release",
        "suspicious_release",
        "standalone",
    ] = "standalone"
    qualityScore: int = 0
    qualityRank: int | None = None
    duplicateConfidence: int = 0
    relatedReleaseCount: int = 0
    bestVersion: bool = False
    fakeFlacStatus: Literal["none", "possible", "likely", "suspicious"] = "none"
    formatSummary: str | None = None
    reasons: list[str] = []
    releaseActions: list[ReleaseActionSchema] = []


class InsightItemSchema(BaseModel):
    id: str
    category: Literal["quality", "duplicate", "suspicious_audio", "collection", "recommendation"]
    severity: Literal["danger", "warning", "success", "neutral"]
    title: str
    message: str
    reasoning: list[str] = []
    confidence: int = 0
    relatedAlbumIds: list[str] = []
    actionable: bool = False
    recommendationType: str | None = None
    generatedAt: str | None = None
    scope: Literal["album", "family"] = "album"


class SmartActionSchema(BaseModel):
    id: str
    type: Literal[
        "keep_recommended",
        "archive_recommended",
        "replace_recommended",
        "cleanup_needed",
        "processing_needed",
        "review_needed",
    ]
    group: Literal["album", "family", "collection"]
    severity: IssueSeverity
    category: Literal["metadata", "artwork", "sequencing", "duplicate", "release_quality", "suspicious_audio", "collection_cleanup", "processing"]
    impact: Literal["cosmetic", "moderate", "important"]
    title: str
    message: str
    reasoning: list[str] = []
    sourceSignals: list[str] = []
    detectedBy: list[str] = []
    tier: Literal["automatic_fix_available", "fix_prepared", "review_needed", "informational"]
    executionMode: Literal["auto_apply_in_cleanup", "staged_confirmation", "manual_only", "none"]
    primaryEligible: bool = True
    autoFixReason: str | None = None
    preparedFix: dict[str, Any] | None = None
    canMusorgFix: bool = False
    fixMethod: Literal["global_cleanup", "manual_review", "external_only"]
    ctaLabel: str | None = None
    ctaIntent: Literal["run_cleanup", "none"] = "none"
    afterAction: str | None = None
    blockingReason: str | None = None
    autoFixStatus: Literal["auto_fix_pending", "auto_fix_attempted", "auto_fix_blocked", "auto_fix_failed", "not_auto_fixable"]
    autoFixSupported: bool = False
    autoFixAttempted: bool = False
    autoFixExplanation: str
    skipReason: Literal["provider_conflict", "confidence_too_low", "track_mapping_ambiguous", "release_structure_mismatch", "unsafe_metadata_overwrite", "provider_data_unavailable", "unsupported_fix_path"] | None = None
    blockingSignals: list[str] = []
    capability: Literal["auto_fixable", "semi_auto_fixable", "manual_review_required", "informational_only"]
    whyMatters: str
    suggestedFix: str
    evidence: list[str] = []
    resolutionConfidence: Literal["low", "medium", "high"]
    confidence: int = 0
    confidenceBand: Literal["low", "medium", "high", "very_high"] = "low"
    affectedAlbumIds: list[str] = []
    actionable: bool = False
    destructive: bool = False
    recommended: bool = False
    reversible: bool = True
    priority: int = 0
    snapshotId: str
    generatedFromSnapshotId: str
    generatedAt: str | None = None
    contextSummary: str | None = None
    dismissible: bool = False
    snoozable: bool = False
    persistent: bool = True
    suppressedByActionId: str | None = None
    suppressedReason: str | None = None
    supersededByActionId: str | None = None


class IssueCountsSchema(BaseModel):
    danger: int
    warning: int
    success: int


class AlbumListItemSchema(BaseModel):
    id: str
    title: str
    artist: str
    year: str
    trackCount: int
    coverUrl: str
    issueCounts: IssueCountsSchema
    status: Literal["ready", "issues"]
    processingState: str | None = None
    outputPath: str | None = None
    provider: str | None = None
    releaseType: str | None = None
    confidenceLevel: Literal["high", "medium", "low", "suspicious"] | None = None
    lowConfidence: bool = False
    metadataIntelligence: MetadataIntelligenceSchema | None = None
    releaseIntelligence: ReleaseIntelligenceSummarySchema | None = None
    topAction: SmartActionSchema | None = None
    actionSummary: list[SmartActionSchema] = []
    actionCount: int = 0


class AlbumsResponse(BaseModel):
    libraryPath: str
    albums: list[AlbumListItemSchema]


class InspectorMetricSchema(BaseModel):
    id: str
    label: str
    value: str
    severity: IssueSeverity


class AlbumInspectorSchema(BaseModel):
    id: str
    coverUrl: str
    title: str
    artist: str
    year: str
    albumArtist: str
    genre: str
    disc: str
    metrics: list[InspectorMetricSchema]
    issues: list[AlbumIssueSchema]
    processingState: str | None = None
    outputPath: str | None = None
    provider: str | None = None
    confidenceLevel: Literal["high", "medium", "low", "suspicious"] | None = None
    lowConfidence: bool = False
    metadataIntelligence: MetadataIntelligenceSchema | None = None
    releaseIntelligence: ReleaseIntelligenceSummarySchema | None = None
    topAction: SmartActionSchema | None = None
    actionSummary: list[SmartActionSchema] = []
    actionCount: int = 0


class AlbumDetailResponse(BaseModel):
    album: AlbumInspectorSchema


class AlbumActionsResponseSchema(BaseModel):
    albumId: str
    snapshotId: str
    topAction: SmartActionSchema | None = None
    actionSummary: list[SmartActionSchema] = []
    actionCount: int = 0
    recommendationSummary: str | None = None
    albumActions: list[SmartActionSchema] = []
    familyActions: list[SmartActionSchema] = []
    suppressedActions: list[SmartActionSchema] = []


class TrackRowSchema(BaseModel):
    id: str
    checked: bool
    index: int
    title: str
    artist: str
    duration: str
    issues: list[AlbumIssueSchema]


class TracksResponse(BaseModel):
    tracks: list[TrackRowSchema]


class RelatedReleaseItemSchema(BaseModel):
    id: str
    releaseFamilyId: str | None = None
    releaseVariantId: str | None = None
    title: str
    artist: str
    year: str
    trackCount: int
    formatSummary: str
    qualityScore: int
    qualityRank: int | None = None
    bestVersion: bool = False
    releaseVariantType: str
    relationshipStatus: str
    duplicateConfidence: int = 0
    fakeFlacStatus: Literal["none", "possible", "likely", "suspicious"] = "none"
    reasons: list[str] = []
    releaseActions: list[ReleaseActionSchema] = []
    current: bool = False


class ReleaseComparisonResponseSchema(BaseModel):
    albumId: str
    releaseFamilyId: str | None = None
    current: RelatedReleaseItemSchema
    family: list[RelatedReleaseItemSchema]
    possibleMatches: list[RelatedReleaseItemSchema] = []


class LogStepSchema(BaseModel):
    id: str
    title: str
    status: str


class LogEntrySchema(BaseModel):
    id: str
    timestamp: str
    severity: str
    source: str
    channel: str = "activity"
    type: str
    stage: str | None = None
    message: str
    payload: dict | None = None
    albumId: str | None = None
    runId: str | None = None
    sequence: int | None = None


class LogsResponse(BaseModel):
    activeRunId: str | None = None
    sessionState: Literal["NO_ACTIVE_RUN", "RUN_START", "RUN_PROGRESS", "RUN_COMPLETE", "RUN_CLEARED"] = "NO_ACTIVE_RUN"
    steps: list[LogStepSchema]
    logs: list[LogEntrySchema]
