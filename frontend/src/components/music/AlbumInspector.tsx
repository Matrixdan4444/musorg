import { AlertTriangle, Check, ChevronDown, Eye, Music4, ShieldCheck, Sparkles, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { CoverImage } from "@/components/music/CoverImage";
import { Panel } from "@/components/Panel";
import { IssueBadge } from "@/components/music/IssueBadge";
import { useI18n } from "@/i18n/useI18n";
import { cn } from "@/lib/cn";
import {
  translateCleanupAction,
  translateConfidenceLabel,
  translateDiffLabel,
  translateIssueLabel,
  translateMatchReason,
  translateProviderName,
  translateProviderReason,
  translateSuspiciousLabel,
  translateSuspiciousMessage,
} from "@/lib/ui-copy";
import type {
  AlbumActionsPayload,
  AlbumInspectorData,
  CleanupAction,
  IssueSeverity,
  InspectorMetric,
  MatchReason,
  MetadataDiffField,
  RelatedReleaseItem,
  ReleaseComparisonPayload,
  SmartAction,
  SuspiciousMetadataItem,
  TrackRow,
} from "@/types/music";

const metricIcon = {
  info: Eye,
  danger: AlertTriangle,
  warning: Music4,
  success: Check,
  neutral: Eye,
} as const;

function MetricChip({
  metric,
  active,
  onClick,
}: {
  metric: InspectorMetric;
  active: boolean;
  onClick: () => void;
}) {
  const Icon = metricIcon[metric.severity];

  return (
    <button
      className={cn(
        "flex items-center justify-center gap-2 rounded-2xl px-3 py-2 text-[12px] font-medium transition",
        metric.severity === "danger" && "bg-danger text-danger-foreground",
        metric.severity === "warning" && "bg-warning text-warning-foreground",
        metric.severity === "success" && "bg-success text-success-foreground",
        metric.severity === "neutral" && "bg-info text-info-foreground",
        active && "ring-1 ring-[hsl(var(--ring)/0.28)]",
      )}
      type="button"
      onClick={onClick}
    >
      <Icon className="h-3.5 w-3.5" />
      <span>{metric.value}</span>
    </button>
  );
}

interface AlbumInspectorProps {
  inspector: AlbumInspectorData;
  tracks: TrackRow[];
  relatedReleases: ReleaseComparisonPayload | null;
  relatedReleasesLoading?: boolean;
  actions: AlbumActionsPayload | null;
  actionsLoading?: boolean;
  stagedOverride: Partial<EditableInspectorFields> | undefined;
  activeMetricFilter: string | null;
  onDismiss: () => void;
  onMetricFilterChange: (value: string | null) => void;
  onSaveOverride: (changes: Partial<EditableInspectorFields>) => void;
  onRevertOverride: () => void;
  onRunCleanup: () => void;
  cleanupRunning?: boolean;
  developerMode?: boolean;
}

export interface EditableInspectorFields {
  albumArtist: string;
  genre: string;
  year: string;
  disc: string;
}

type IntelligenceSectionId =
  | "metadataDiff"
  | "whatChanged"
  | "matchReasoning"
  | "providerDecisions"
  | "suspiciousMetadata";

const DEFAULT_EXPANDED_SECTIONS: Record<IntelligenceSectionId, boolean> = {
  metadataDiff: false,
  whatChanged: false,
  matchReasoning: false,
  providerDecisions: false,
  suspiciousMetadata: false,
};

export function AlbumInspector({
  inspector,
  tracks,
  relatedReleases,
  relatedReleasesLoading,
  actions,
  actionsLoading,
  stagedOverride,
  activeMetricFilter,
  onDismiss,
  onMetricFilterChange,
  onSaveOverride,
  onRevertOverride,
  onRunCleanup,
  cleanupRunning,
  developerMode,
}: AlbumInspectorProps) {
  const { t } = useI18n();
  const [coverPreviewOpen, setCoverPreviewOpen] = useState(false);
  const [issuesOpen, setIssuesOpen] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<IntelligenceSectionId, boolean>>(DEFAULT_EXPANDED_SECTIONS);
  const [form, setForm] = useState<EditableInspectorFields>({
    albumArtist: inspector.albumArtist,
    genre: inspector.genre,
    year: inspector.year,
    disc: inspector.disc,
  });

  const effectiveValues = useMemo<EditableInspectorFields>(() => ({
    albumArtist: stagedOverride?.albumArtist ?? inspector.albumArtist,
    genre: stagedOverride?.genre ?? inspector.genre,
    year: stagedOverride?.year ?? inspector.year,
    disc: stagedOverride?.disc ?? inspector.disc,
  }), [inspector, stagedOverride]);

  useEffect(() => {
    setForm(effectiveValues);
  }, [effectiveValues, inspector.id]);

  useEffect(() => {
    setExpandedSections(DEFAULT_EXPANDED_SECTIONS);
  }, [inspector.id]);

  const dirtyFields = useMemo(() => ({
    albumArtist: form.albumArtist.trim() !== (effectiveValues.albumArtist || "").trim(),
    genre: form.genre.trim() !== (effectiveValues.genre || "").trim(),
    year: form.year.trim() !== (effectiveValues.year || "").trim(),
    disc: form.disc.trim() !== (effectiveValues.disc || "").trim(),
  }), [effectiveValues, form]);

  const hasDirtyForm = Object.values(dirtyFields).some(Boolean);

  const filteredIssues = useMemo(() => {
    if (!activeMetricFilter || activeMetricFilter === "info") {
      return inspector.issues;
    }
    if (activeMetricFilter === "success") {
      return [];
    }
    return inspector.issues.filter((issue) => issue.severity === activeMetricFilter);
  }, [activeMetricFilter, inspector.issues]);

  const issueDetails = useMemo(() => {
    return filteredIssues.map((issue) => ({
      issue,
      tracks: tracks.filter((track) => track.issues.some((trackIssue) => trackIssue.severity === issue.severity)),
      proposedFix: (() => {
        const resolved = t(`inspector.fixes.${issue.id}` as never);
        return resolved.startsWith("inspector.fixes.") ? t("inspector.proposedFixFallback") : resolved;
      })(),
    }));
  }, [filteredIssues, t, tracks]);

  const intelligence = inspector.metadataIntelligence;
  const isMissingOutput = inspector.processingState === "missing_output";
  const hasActiveIntelligence = Boolean(intelligence);
  const isIntelligencePending = !hasActiveIntelligence
    && ["scanning", "matching", "writing"].includes(inspector.processingState ?? "");

  function handleSave() {
    const nextChanges: Partial<EditableInspectorFields> = {};
    if (dirtyFields.albumArtist) {
      nextChanges.albumArtist = form.albumArtist.trim();
    }
    if (dirtyFields.genre) {
      nextChanges.genre = form.genre.trim();
    }
    if (dirtyFields.year) {
      nextChanges.year = form.year.trim();
    }
    if (dirtyFields.disc) {
      nextChanges.disc = form.disc.trim();
    }
    onSaveOverride(nextChanges);
  }

  function handleRevert() {
    setForm(effectiveValues);
    onRevertOverride();
  }

  function toggleIntelligenceSection(sectionId: IntelligenceSectionId) {
    setExpandedSections((current) => ({
      ...current,
      [sectionId]: !current[sectionId],
    }));
  }

  return (
    <>
      <Panel className="flex h-full min-h-0 flex-col p-4">
        <button
          className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition hover:bg-surface-subtle/75 hover:text-[hsl(var(--text-strong))]"
          type="button"
          onClick={onDismiss}
        >
          ×
        </button>

        <div className="mt-2 flex justify-center">
          <button className="w-full max-w-[208px]" type="button" onClick={() => setCoverPreviewOpen(true)}>
            <CoverImage
              alt={t("albumCard.coverAlt", { title: inspector.title })}
              className="aspect-square rounded-[24px] border border-border-soft/75"
              src={inspector.coverUrl}
            />
          </button>
        </div>

        <div className="mt-5 space-y-1.5">
          <h2 className="break-words text-[16px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
            {inspector.title}
          </h2>
          <p className="break-words text-[13px] text-[hsl(var(--text-base))]">{inspector.artist}</p>
          <p className="overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-muted-foreground">{inspector.year}</p>
        </div>

        <div className="mt-5 grid grid-cols-4 gap-2">
          {inspector.metrics.map((metric) => (
            <MetricChip
              key={metric.id}
              active={activeMetricFilter === metric.severity || (activeMetricFilter === null && metric.id === "info")}
              metric={metric}
              onClick={() => onMetricFilterChange(activeMetricFilter === metric.severity ? null : metric.severity)}
            />
          ))}
        </div>

        <div className="mt-5 space-y-2">
          <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
            {t("inspector.albumArtist")}
          </p>
          <div className={cn("rounded-[18px] border border-border-soft/75 bg-surface-subtle/85 px-4 py-3", dirtyFields.albumArtist && "border-[hsl(var(--ring)/0.6)]")}>
            <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
              <UserRound className="h-3.5 w-3.5" />
              {t("inspector.artist")}
            </span>
            <input
              className="mt-2 w-full bg-transparent text-[13px] text-[hsl(var(--text-base))] outline-none"
              value={form.albumArtist}
              onChange={(event) => setForm((current) => ({ ...current, albumArtist: event.target.value }))}
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-[minmax(0,1fr)_64px_64px] gap-2">
          {(["genre", "year", "disc"] as const).map((field) => (
            <label
              key={field}
              className={cn(
                "rounded-[18px] border border-border-soft/75 bg-surface-subtle/85 px-3 py-3",
                dirtyFields[field] && "border-[hsl(var(--ring)/0.6)]",
              )}
            >
              <span className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                {field === "genre" ? t("inspector.genre") : field === "year" ? t("inspector.year") : t("inspector.disc")}
              </span>
              <input
                className="mt-2 w-full bg-transparent text-[13px] text-[hsl(var(--text-base))] outline-none"
                value={form[field]}
                onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.value }))}
              />
            </label>
          ))}
        </div>

        <div className="mt-4 flex gap-2">
          <button
            className="app-button-primary rounded-2xl px-4 py-2 text-[12px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            disabled={!hasDirtyForm}
            onClick={handleSave}
          >
            {t("inspector.saveChanges")}
          </button>
          <button
            className="app-button-secondary rounded-2xl px-4 py-2 text-[12px] transition"
            type="button"
            onClick={handleRevert}
          >
            {t("inspector.revertChanges")}
          </button>
        </div>

        {isMissingOutput ? (
          <div className="mt-5 rounded-[20px] border border-[hsl(var(--warning-border)/0.6)] bg-warning px-4 py-3">
            <p className="text-[12px] font-semibold text-warning-foreground">{t("inspector.missingOutputTitle")}</p>
            <p className="mt-1 text-[12px] leading-5 text-warning-foreground">{t("inspector.missingOutputMessage")}</p>
          </div>
        ) : null}

        {inspector.lowConfidence ? (
          <div className="mt-5 rounded-[20px] border border-[hsl(var(--warning-border)/0.6)] bg-warning px-4 py-3">
            <p className="text-[12px] font-semibold text-warning-foreground">{t("inspector.lowConfidenceTitle")}</p>
            <p className="mt-1 text-[12px] leading-5 text-warning-foreground">{t("inspector.lowConfidenceMessage")}</p>
          </div>
        ) : null}

        {developerMode && (hasActiveIntelligence || isIntelligencePending) ? (
          <DiagnosticsSection
            intelligence={intelligence ?? null}
            isPending={isIntelligencePending}
            expandedSections={expandedSections}
            onToggle={toggleIntelligenceSection}
          />
        ) : null}

        {inspector.releaseIntelligence || relatedReleases ? (
          <div className="mt-5 space-y-3">
            <RecommendationsSection
          data={actions}
          inlineActions={inspector.actionSummary ?? []}
          loading={actionsLoading}
          onRunCleanup={onRunCleanup}
          cleanupRunning={cleanupRunning}
        />
            <VariantsSection data={relatedReleases} loading={relatedReleasesLoading} />
          </div>
        ) : null}

        <div className="mt-5 flex min-h-0 flex-1 flex-col rounded-[22px] border border-border-soft/75 bg-surface-subtle/85 p-4">
          <p className="text-[12px] font-medium text-[hsl(var(--text-strong))]">{t("inspector.issues")}</p>
          {filteredIssues.length === 0 ? (
            <div className="mt-3 flex min-h-0 flex-1 items-center rounded-2xl border border-dashed border-border-soft/75 px-3 py-4 text-[12px] text-muted-foreground">
              {t("inspector.noIssues")}
            </div>
          ) : (
            <div className="mt-3 min-h-0 flex-1 space-y-2.5 overflow-y-auto pr-1">
          {filteredIssues.map((issue) => (
                <div key={issue.id} className="min-w-0 overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-contrast/90 px-3 py-3 text-[12px] text-[hsl(var(--text-base))]">
                  <div className="shrink-0">
                    <IssueBadge compact issue={issue} className="px-1.5" />
                  </div>
                  <p className="mt-2 min-w-0 whitespace-normal break-words text-[12px] leading-5 [word-break:break-word]">
                    {translateIssueLabel(issue.id, issue.label, t)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          className="mt-4 flex items-center justify-between rounded-[20px] border border-border-soft/75 bg-surface-subtle/85 px-4 py-3 text-[12px] transition hover:bg-surface-subtle"
          type="button"
          onClick={() => setIssuesOpen(true)}
        >
          <span className="font-medium text-[hsl(var(--accent))]">{t("inspector.viewAllIssues")}</span>
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-accent text-accent-foreground">
            {filteredIssues.length}
          </span>
        </button>
      </Panel>

      {coverPreviewOpen ? (
        <ModalFrame title={t("inspector.coverPreview")} onClose={() => setCoverPreviewOpen(false)}>
          <CoverImage alt={t("albumCard.coverAlt", { title: inspector.title })} className="mx-auto aspect-square max-w-[420px] rounded-[24px]" src={inspector.coverUrl} />
        </ModalFrame>
      ) : null}

      {issuesOpen ? (
        <ModalFrame title={t("inspector.albumIssues")} onClose={() => setIssuesOpen(false)}>
          <div className="space-y-4">
            {issueDetails.length === 0 ? (
              <div className="text-[13px] text-muted-foreground">{t("inspector.noDetailedIssues")}</div>
            ) : (
              issueDetails.map(({ issue, tracks: relatedTracks, proposedFix }) => (
                <div key={issue.id} className="min-w-0 overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-subtle/85 p-4">
                  <div className="shrink-0">
                    <IssueBadge compact issue={issue} className="px-1.5" />
                  </div>
                  <p className="mt-2 min-w-0 whitespace-normal break-words text-[13px] font-semibold leading-6 text-[hsl(var(--text-strong))] [word-break:break-word]">
                    {translateIssueLabel(issue.id, issue.label, t)}
                  </p>
                  <p className="mt-3 min-w-0 whitespace-normal break-words text-[12px] leading-5 text-muted-foreground [overflow-wrap:anywhere]">{t("inspector.severity", { value: t(`inspector.severityValues.${issue.severity}` as never) })}</p>
                  <p className="mt-2 min-w-0 whitespace-normal break-words text-[12px] leading-6 text-[hsl(var(--text-base))] [overflow-wrap:anywhere]">{t("inspector.proposedFix", { value: proposedFix })}</p>
                  <div className="mt-3 min-w-0 space-y-1 text-[12px] text-muted-foreground">
                    <p>{t("inspector.affectedTracks")}</p>
                    {relatedTracks.length === 0 ? (
                      <p>{t("inspector.albumLevelIssue")}</p>
                    ) : (
                      relatedTracks.map((track) => <p key={track.id} className="min-w-0 whitespace-normal break-words leading-5 [overflow-wrap:anywhere]">• {track.index}. {track.title}</p>)
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </ModalFrame>
      ) : null}
    </>
  );
}

function DiagnosticsSection({
  intelligence,
  isPending,
  expandedSections,
  onToggle,
}: {
  intelligence: AlbumInspectorData["metadataIntelligence"] | null;
  isPending: boolean;
  expandedSections: Record<IntelligenceSectionId, boolean>;
  onToggle: (id: IntelligenceSectionId) => void;
}) {
  const { t } = useI18n();
  return (
    <section className="min-w-0 overflow-visible rounded-[20px] border border-border-soft/75 bg-surface-subtle/85 px-4 py-4">
      <p className="text-[12px] font-medium text-[hsl(var(--text-strong))]">{t("inspector.diagnostics")}</p>
      <div className="mt-3 space-y-3">
        <IntelligenceSummary
          confidenceLevel={intelligence?.confidence.level}
          confidenceLabel={intelligence?.confidence.label ?? t("inspector.pendingSummary")}
          provider={intelligence?.providerDecisions.metadataProvider}
          artworkProvider={intelligence?.providerDecisions.artworkProvider}
          pending={isPending}
        />
        <IntelligenceSection
          id="metadataDiff"
          title={t("inspector.metadataDiff")}
          count={intelligence?.diff.length ?? 0}
          expanded={expandedSections.metadataDiff}
          onToggle={onToggle}
        >
          {isPending ? (
            <PendingMessage label={t("inspector.pendingDiff")} />
          ) : (
            <MetadataDiffList rows={intelligence?.diff ?? []} emptyLabel={t("inspector.noMetadataDiff")} />
          )}
        </IntelligenceSection>
        <IntelligenceSection
          id="whatChanged"
          title={t("inspector.whatChanged")}
          count={intelligence?.cleanupActions.length ?? 0}
          expanded={expandedSections.whatChanged}
          onToggle={onToggle}
        >
          {isPending ? (
            <PendingMessage label={t("inspector.pendingChanges")} />
          ) : (
            <CleanupActionList
              actions={intelligence?.cleanupActions ?? []}
              autoFixLabel={t("inspector.autoFix")}
              manualOverrideLabel={t("inspector.manualOverride")}
            />
          )}
        </IntelligenceSection>
        <IntelligenceSection
          id="matchReasoning"
          title={t("inspector.matchReasoning")}
          count={intelligence?.matchReasoning.length ?? 0}
          expanded={expandedSections.matchReasoning}
          onToggle={onToggle}
        >
          {isPending ? (
            <PendingMessage label={t("inspector.pendingReasoning")} />
          ) : (
            <MatchReasonList reasons={intelligence?.matchReasoning ?? []} />
          )}
        </IntelligenceSection>
        <IntelligenceSection
          id="providerDecisions"
          title={t("inspector.providerDecisions")}
          count={((intelligence?.providerDecisions.rejectedProviders?.length ?? 0) + (intelligence ? 1 : 0))}
          expanded={expandedSections.providerDecisions}
          onToggle={onToggle}
        >
          {isPending ? (
            <PendingMessage label={t("inspector.pendingProviders")} />
          ) : (
            <ProviderDecisionPanel
              provider={intelligence?.providerDecisions.metadataProvider}
              artworkProvider={intelligence?.providerDecisions.artworkProvider}
              path={intelligence?.providerDecisions.path}
              rejected={intelligence?.providerDecisions.rejectedProviders ?? []}
            />
          )}
        </IntelligenceSection>
        <IntelligenceSection
          id="suspiciousMetadata"
          title={t("inspector.suspiciousMetadata")}
          count={intelligence?.suspiciousMetadata.length ?? 0}
          expanded={expandedSections.suspiciousMetadata}
          onToggle={onToggle}
        >
          {isPending ? (
            <PendingMessage label={t("inspector.pendingSuspicious")} />
          ) : (
            <SuspiciousMetadataList
              items={intelligence?.suspiciousMetadata ?? []}
              emptyLabel={t("inspector.noSuspiciousMetadata")}
            />
          )}
        </IntelligenceSection>
      </div>
    </section>
  );
}

function RecommendationsSection({
  data,
  inlineActions,
  loading,
  onRunCleanup,
  cleanupRunning,
}: {
  data: AlbumActionsPayload | null;
  inlineActions: SmartAction[];
  loading?: boolean | undefined;
  onRunCleanup: () => void;
  cleanupRunning: boolean | undefined;
}) {
  const { t } = useI18n();
  const actions = data ? [...data.albumActions, ...data.familyActions] : inlineActions;
  const primaryActions = actions.filter((action) => action.primaryEligible).slice(0, 3);

  if (!loading && !primaryActions.length) {
    return null;
  }

  return (
    <section className="min-w-0 overflow-visible rounded-[20px] border border-border-soft/75 bg-surface-subtle/85 px-4 py-4">
      <p className="text-[12px] font-medium text-[hsl(var(--text-strong))]">{t("inspector.recommendations")}</p>
      {loading ? (
        <p className="mt-3 text-[12px] text-muted-foreground">{t("common.loading")}</p>
      ) : (
        <div className="mt-3 space-y-2.5">
          {primaryActions.map((action) => (
            <RecommendationCard
              key={action.id}
              action={action}
              onRunCleanup={onRunCleanup}
              cleanupRunning={cleanupRunning}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function VariantsSection({
  data,
  loading,
}: {
  data: ReleaseComparisonPayload | null;
  loading?: boolean | undefined;
}) {
  const { t } = useI18n();
  const [compareOpen, setCompareOpen] = useState(false);
  const suggestions = data ? summarizeVariantSuggestions(data, t) : [];

  if (!loading && (!data || suggestions.length === 0)) {
    return null;
  }

  return (
    <>
    <section className="min-w-0 overflow-visible rounded-[20px] border border-border-soft/75 bg-surface-subtle/85 px-4 py-4">
      <p className="text-[12px] font-medium text-[hsl(var(--text-strong))]">{t("inspector.duplicatesVariants")}</p>
      {loading ? (
        <p className="mt-3 text-[12px] text-muted-foreground">{t("common.loading")}</p>
      ) : (
        <div className="mt-3 space-y-2.5">
          {suggestions.map((item, index) => (
            <p key={`${item}-${index}`} className="rounded-2xl border border-border-soft/75 bg-surface-contrast/90 px-3 py-3 text-[12px] leading-6 text-[hsl(var(--text-base))]">
              {item}
            </p>
          ))}
          <button
            className="app-button-secondary rounded-2xl px-3 py-2 text-[12px] transition"
            type="button"
            onClick={() => setCompareOpen(true)}
          >
            {t("inspector.compare")}
          </button>
        </div>
      )}
    </section>
    {compareOpen && data ? (
      <ModalFrame title={t("inspector.duplicatesVariants")} onClose={() => setCompareOpen(false)}>
        <div className="space-y-3">
          <ReleaseComparisonCard item={data.current} emphasis="current" />
          {data.family.filter((item) => !item.current).slice(0, 2).map((item) => (
            <ReleaseComparisonCard key={item.id} item={item} />
          ))}
          {data.possibleMatches.slice(0, 1).map((item) => (
            <ReleaseComparisonCard key={`possible-${item.id}`} item={item} />
          ))}
        </div>
      </ModalFrame>
    ) : null}
    </>
  );
}

function RecommendationCard({
  action,
  onRunCleanup,
  cleanupRunning,
}: {
  action: SmartAction;
  onRunCleanup: () => void;
  cleanupRunning: boolean | undefined;
}) {
  const { t } = useI18n();
  const followUp = action.canMusorgFix
    ? action.afterAction || action.suggestedFix
    : action.blockingReason || action.suggestedFix;
  return (
    <div className={cn("rounded-2xl border px-3 py-3", insightCardClassName(action.severity))}>
      <div className="space-y-2">
        <p className="text-[12px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">{action.title}</p>
        <p className="text-[12px] leading-6 text-[hsl(var(--text-base))]">{action.message}</p>
        {action.canMusorgFix && action.ctaIntent === "run_cleanup" && action.ctaLabel ? (
          <button
            className="app-button-primary inline-flex h-10 items-center justify-center rounded-2xl px-4 text-[12px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-60"
            type="button"
            onClick={onRunCleanup}
            disabled={cleanupRunning}
          >
            {cleanupRunning ? t("import.cleaning") : action.ctaLabel}
          </button>
        ) : null}
        {followUp ? (
          <p className="text-[12px] leading-6 text-muted-foreground">{followUp}</p>
        ) : null}
      </div>
    </div>
  );
}

function ReleaseComparisonCard({
  item,
  emphasis,
}: {
  item: RelatedReleaseItem;
  emphasis?: "current";
}) {
  const { t } = useI18n();
  return (
    <div className={cn(
      "min-w-0 overflow-hidden rounded-2xl border px-3 py-3",
      emphasis === "current"
        ? "border-[hsl(var(--success-border)/0.55)] bg-success/55"
        : "border-border-soft/75 bg-surface-contrast/90",
    )}>
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex shrink-0 whitespace-nowrap rounded-full bg-info px-2 py-1 text-[10px] font-medium text-info-foreground">
          {t(`inspector.releaseStatus.${item.relationshipStatus}` as never)}
        </span>
        <span className="inline-flex shrink-0 whitespace-nowrap rounded-full bg-success px-2 py-1 text-[10px] font-medium text-success-foreground">
          {t(`inspector.releaseVariant.${item.releaseVariantType}` as never)}
        </span>
        <span className="inline-flex shrink-0 whitespace-nowrap rounded-full bg-surface-selected/95 px-2 py-1 text-[10px] font-medium text-[hsl(var(--text-strong))]">
          {item.formatSummary}
        </span>
      </div>
      <p className="mt-2 min-w-0 whitespace-normal break-words text-[12px] font-medium leading-5 text-[hsl(var(--text-strong))] [word-break:break-word]">
        {item.title}
      </p>
      <p className="mt-1 text-[12px] text-muted-foreground">{item.artist} · {item.year}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded-xl border border-border-soft/75 bg-surface-subtle/85 px-3 py-2 text-[12px] text-[hsl(var(--text-base))]">
          {t("inspector.releaseTrackCount", { count: item.trackCount })}
        </div>
        <div className="rounded-xl border border-border-soft/75 bg-surface-subtle/85 px-3 py-2 text-[12px] text-[hsl(var(--text-base))]">
          {item.formatSummary}
        </div>
      </div>
      {item.reasons.length ? (
        <div className="mt-3 space-y-1">
          {item.reasons.slice(0, 3).map((reason, index) => (
            <p key={`${item.id}-reason-${index}`} className="min-w-0 whitespace-normal break-words text-[12px] leading-6 text-[hsl(var(--text-base))] [overflow-wrap:anywhere]">
              {reason}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function summarizeVariantSuggestions(
  data: ReleaseComparisonPayload,
  t: ReturnType<typeof useI18n>["t"],
): string[] {
  const suggestions: string[] = [];
  const candidates = [...data.family.filter((item) => !item.current), ...data.possibleMatches];
  const bestCandidate = candidates[0];
  if (!bestCandidate) {
    return suggestions;
  }
  if (bestCandidate.relationshipStatus === "better_version_available") {
    suggestions.push(t("inspector.variantSuggestion.betterVersion"));
  }
  if (bestCandidate.fakeFlacStatus === "none" && /flac/i.test(bestCandidate.formatSummary) && !/flac/i.test(data.current.formatSummary)) {
    suggestions.push(t("inspector.variantSuggestion.flacAvailable"));
  }
  if (bestCandidate.releaseActions.some((item) => item.id === "replace_artwork")) {
    suggestions.push(t("inspector.variantSuggestion.betterArtwork"));
  }
  return Array.from(new Set(suggestions));
}

function IntelligenceSummary({
  confidenceLevel,
  confidenceLabel,
  confidenceReasons,
  provider,
  artworkProvider,
  pending,
}: {
  confidenceLevel?: string | null | undefined;
  confidenceLabel: string;
  confidenceReasons?: string[] | undefined;
  provider?: string | null | undefined;
  artworkProvider?: string | null | undefined;
  pending?: boolean;
}) {
  const { t } = useI18n();
  const confidenceSummary = pending
    ? t("inspector.pendingSummary")
    : translateConfidenceLabel(confidenceLevel, confidenceLabel, t);
  const confidenceTooltip = pending
    ? t("inspector.pendingSummary")
    : confidenceReasons?.length
      ? confidenceReasons.join("\n")
      : confidenceSummary;
  return (
    <div className="flex flex-wrap gap-2">
      <SummaryPill
        icon={<ShieldCheck className="h-3.5 w-3.5" />}
        label={confidenceSummary}
        tone={confidenceLevel}
        hint={confidenceTooltip}
      />
      <SummaryPill
        icon={<Sparkles className="h-3.5 w-3.5" />}
        label={pending ? t("inspector.pendingProviders") : t("inspector.providerLabels.metadataSummary", { provider: translateProviderName(provider, t) })}
      />
      <SummaryPill
        icon={<Eye className="h-3.5 w-3.5" />}
        label={pending ? t("inspector.pendingArtwork") : t("inspector.providerLabels.artworkSummary", { provider: translateProviderName(artworkProvider, t) })}
      />
    </div>
  );
}

function SummaryPill({
  icon,
  label,
  hint,
  tone,
}: {
  icon: ReactNode;
  label: string;
  hint?: string;
  tone?: string | null | undefined;
}) {
  const toneClassName = tone === "suspicious"
    ? "border-[hsl(var(--danger-border)/0.55)] bg-danger text-danger-foreground"
    : tone === "high"
      ? "border-[hsl(var(--success-border)/0.55)] bg-success text-success-foreground"
      : tone === "medium"
        ? "border-[hsl(var(--warning-border)/0.55)] bg-warning text-warning-foreground"
        : tone === "low"
          ? "border-[hsl(var(--warning-border)/0.55)] bg-warning text-warning-foreground"
          : "border-border-soft/75 bg-surface-subtle/85 text-[hsl(var(--text-base))]";
  return (
    <div
      className={cn("flex min-w-[11rem] max-w-full flex-1 basis-[11rem] items-center gap-2 overflow-visible rounded-[18px] border px-3 py-2 text-[12px]", toneClassName)}
    >
      <span className="shrink-0 text-[hsl(var(--accent))]">{icon}</span>
      <span className="min-w-0 overflow-hidden whitespace-normal break-words leading-5">{label}</span>
      {hint ? <HintDot text={hint} /> : null}
    </div>
  );
}

function HintDot({ text }: { text: string }) {
  return (
    <span className="relative inline-flex shrink-0">
      <button
        aria-label={text}
        className="peer inline-flex h-4 w-4 shrink-0 cursor-help select-none items-center justify-center rounded-full border border-border-soft/80 bg-surface-subtle/85 text-[10px] font-semibold leading-none text-muted-foreground transition hover:border-border-strong/85 hover:bg-surface-strong/75 hover:text-[hsl(var(--text-strong))] focus:outline-none focus-visible:border-border-strong/85 focus-visible:bg-surface-strong/75 focus-visible:text-[hsl(var(--text-strong))]"
        type="button"
      >
        ?
      </button>
      <span className="app-tooltip-surface pointer-events-none absolute bottom-[calc(100%+0.5rem)] right-0 z-30 w-[16rem] max-w-[min(16rem,calc(100vw-2rem))] translate-y-1 rounded-xl px-3 py-2 text-left text-[11px] font-normal leading-5 text-[hsl(var(--text-base))] opacity-0 transition duration-150 peer-hover:translate-y-0 peer-hover:opacity-100 peer-focus-visible:translate-y-0 peer-focus-visible:opacity-100">
        {text}
      </span>
    </span>
  );
}

function insightCardClassName(severity: IssueSeverity) {
  if (severity === "danger") {
    return "border-[hsl(var(--danger-border)/0.55)] bg-danger";
  }
  if (severity === "warning") {
    return "border-[hsl(var(--warning-border)/0.55)] bg-warning";
  }
  if (severity === "success") {
    return "border-[hsl(var(--success-border)/0.55)] bg-success";
  }
  return "border-border-soft/75 bg-surface-contrast/90";
}

function insightPillClassName(severity: IssueSeverity) {
  if (severity === "danger") {
    return "bg-danger text-danger-foreground";
  }
  if (severity === "warning") {
    return "bg-warning text-warning-foreground";
  }
  if (severity === "success") {
    return "bg-success text-success-foreground";
  }
  return "bg-info text-info-foreground";
}

function IntelligenceSection({
  id,
  title,
  count,
  expanded,
  onToggle,
  children,
}: {
  id: IntelligenceSectionId;
  title: string;
  count: number;
  expanded: boolean;
  onToggle: (id: IntelligenceSectionId) => void;
  children: ReactNode;
}) {
  const contentId = `${id}-content`;
  return (
    <section className="min-w-0 overflow-hidden rounded-[20px] border border-border-soft/75 bg-surface-subtle/85">
      <button
        aria-controls={contentId}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-3 rounded-[20px] px-4 py-3 text-left text-[12px] font-medium text-[hsl(var(--text-strong))] transition hover:bg-surface-subtle focus:outline-none focus-visible:ring-1 focus-visible:ring-[hsl(var(--ring)/0.25)]"
        type="button"
        onClick={() => onToggle(id)}
      >
        <span className="min-w-0 flex-1 break-words">{title}</span>
        <span className="flex shrink-0 items-center gap-2 text-muted-foreground">
          <span>{count}</span>
          <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", expanded && "rotate-180")} />
        </span>
      </button>
      {expanded ? (
        <div id={contentId} className="min-w-0 overflow-hidden border-t border-border-soft/75 px-4 py-3">
          {children}
        </div>
      ) : null}
    </section>
  );
}

function PendingMessage({ label }: { label: string }) {
  return <p className="min-w-0 break-words text-[12px] text-muted-foreground">{label}</p>;
}

function MetadataDiffList({ rows, emptyLabel }: { rows: MetadataDiffField[]; emptyLabel: string }) {
  const { t } = useI18n();
  if (rows.length === 0) {
    return <p className="text-[12px] text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <div className="min-w-0 space-y-3">
      {rows.map((row) => (
        <div key={row.id} className="min-w-0 overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-contrast/90 px-3 py-3">
          <p className="min-w-0 break-words text-[12px] font-medium text-[hsl(var(--text-strong))]">{translateDiffLabel(row, t)}</p>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">{t("inspector.beforeLabel")}</p>
              <p className="mt-1 min-w-0 break-words whitespace-normal text-[12px] text-[hsl(var(--text-base))]">{row.before}</p>
            </div>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">{t("inspector.afterLabel")}</p>
              <p className="mt-1 min-w-0 break-words whitespace-normal text-[12px] text-[hsl(var(--text-strong))]">{row.after}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CleanupActionList({
  actions,
  autoFixLabel,
  manualOverrideLabel,
}: {
  actions: CleanupAction[];
  autoFixLabel: string;
  manualOverrideLabel: string;
}) {
  const { t } = useI18n();
  return (
    <div className="min-w-0 space-y-2">
      {actions.map((action, index) => {
        const copy = translateCleanupAction(action, t);
        return (
          <div key={`${action.kind}-${index}`} className="min-w-0 overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-contrast/90 px-3 py-3">
            <div className="shrink-0">
              <span
                className={cn(
                  "inline-flex shrink-0 whitespace-nowrap rounded-full px-2 py-1 text-[10px] font-medium",
                  action.origin === "manual_override"
                    ? "bg-surface-selected/95 text-[hsl(var(--text-strong))]"
                    : "bg-success text-success-foreground",
                )}
              >
                {action.origin === "manual_override" ? manualOverrideLabel : autoFixLabel}
              </span>
            </div>
            <p className="mt-2 min-w-0 whitespace-normal break-words text-[12px] font-medium leading-5 text-[hsl(var(--text-strong))] [word-break:break-word]">
              {copy.title}
            </p>
            {copy.description ? (
              <p className="mt-2 min-w-0 whitespace-normal break-words text-[12px] leading-6 text-[hsl(var(--text-base))] [overflow-wrap:anywhere]">
                {copy.description}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function MatchReasonList({ reasons }: { reasons: MatchReason[] }) {
  const { t } = useI18n();
  return (
    <div className="min-w-0 space-y-2">
      {reasons.map((reason, index) => (
        <div key={`${reason.provider}-${index}`} className="min-w-0 overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-contrast/90 px-3 py-3">
          <p className="min-w-0 break-words text-[11px] uppercase tracking-[0.08em] text-muted-foreground">{translateProviderName(reason.provider, t)}</p>
          <p className="mt-1 min-w-0 break-words whitespace-normal text-[12px] text-[hsl(var(--text-base))]">{translateMatchReason(reason, t)}</p>
        </div>
      ))}
    </div>
  );
}

function ProviderDecisionPanel({
  provider,
  artworkProvider,
  path,
  rejected,
}: {
  provider?: string | null | undefined;
  artworkProvider?: string | null | undefined;
  path?: string | null | undefined;
  rejected: { provider: string; message: string }[];
}) {
  const { t } = useI18n();
  return (
    <div className="min-w-0 space-y-3">
      <div className="min-w-0 overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-contrast/90 px-3 py-3 text-[12px] text-[hsl(var(--text-base))]">
        <p className="min-w-0 break-words whitespace-normal">{t("inspector.providerLabels.metadataLine", { provider: translateProviderName(provider, t) })}</p>
        <p className="mt-1 min-w-0 break-words whitespace-normal">{t("inspector.providerLabels.artworkLine", { provider: translateProviderName(artworkProvider, t) })}</p>
        {path ? <p className="mt-1 min-w-0 break-words whitespace-normal text-muted-foreground">{t("inspector.providerLabels.resolutionPath", { path })}</p> : null}
      </div>
      {rejected.map((item, index) => (
        <div key={`${item.provider}-${index}`} className="min-w-0 overflow-hidden rounded-2xl border border-[hsl(var(--danger-border)/0.55)] bg-danger px-3 py-3 text-[12px] text-danger-foreground">
          <p className="min-w-0 break-words font-medium">{translateProviderName(item.provider, t)}</p>
          <p className="mt-1 min-w-0 break-words whitespace-normal">{translateProviderReason(item.message, t)}</p>
        </div>
      ))}
    </div>
  );
}

function SuspiciousMetadataList({
  items,
  emptyLabel,
}: {
  items: SuspiciousMetadataItem[];
  emptyLabel: string;
}) {
  const { t } = useI18n();
  if (items.length === 0) {
    return <p className="text-[12px] text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <div className="min-w-0 space-y-2">
      {items.map((item) => (
        <div key={item.id} className="min-w-0 overflow-hidden rounded-2xl border border-border-soft/75 bg-surface-contrast/90 px-3 py-3">
          <div className="shrink-0">
            <IssueBadge compact issue={{ id: item.id, label: translateSuspiciousLabel(item, t), severity: item.severity }} className="px-1.5" />
          </div>
          <p className="mt-2 min-w-0 whitespace-normal break-words text-[12px] font-medium leading-5 text-[hsl(var(--text-strong))] [word-break:break-word]">
            {translateSuspiciousLabel(item, t)}
          </p>
          <p className="mt-2 min-w-0 whitespace-normal break-words text-[12px] leading-6 text-[hsl(var(--text-base))] [overflow-wrap:anywhere]">
            {translateSuspiciousMessage(item, t)}
          </p>
        </div>
      ))}
    </div>
  );
}

function ModalFrame({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="app-modal-overlay fixed inset-0 z-50 flex items-center justify-center px-4 py-6">
      <Panel className="app-modal-panel flex max-h-[80vh] w-full max-w-[720px] flex-col p-0">
        <div className="flex items-center justify-between border-b border-border-soft/75 px-5 py-4">
          <h2 className="text-[15px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">{title}</h2>
          <button
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition hover:bg-surface-subtle/75 hover:text-[hsl(var(--text-strong))]"
            type="button"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto px-5 py-4">{children}</div>
      </Panel>
    </div>
  );
}
