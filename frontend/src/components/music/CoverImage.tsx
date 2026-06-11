import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { resolveApiUrl } from "@/lib/api/client";
import { cn } from "@/lib/cn";

interface CoverImageProps {
  src: string;
  alt: string;
  className?: string;
  imageClassName?: string;
  compact?: boolean;
  priority?: boolean;
}

const loadedCoverSrcCache = new Set<string>();
const failedCoverSrcCache = new Set<string>();
const pendingCoverWarmups = new Map<string, Promise<void>>();

function markCoverLoaded(src: string) {
  failedCoverSrcCache.delete(src);
  loadedCoverSrcCache.add(src);
}

function markCoverFailed(src: string) {
  loadedCoverSrcCache.delete(src);
  failedCoverSrcCache.add(src);
}

export function warmCoverImage(src: string) {
  const resolvedSrc = resolveApiUrl(src);

  if (!resolvedSrc || typeof window === "undefined") {
    return Promise.resolve();
  }

  if (loadedCoverSrcCache.has(resolvedSrc) || failedCoverSrcCache.has(resolvedSrc)) {
    return Promise.resolve();
  }

  const pending = pendingCoverWarmups.get(resolvedSrc);
  if (pending) {
    return pending;
  }

  const image = new window.Image();
  image.decoding = "async";

  const warmup = new Promise<void>((resolve) => {
    image.onload = () => {
      const finish = () => {
        markCoverLoaded(resolvedSrc);
        resolve();
      };

      if (typeof image.decode === "function") {
        void image.decode().catch(() => undefined).finally(finish);
        return;
      }

      finish();
    };

    image.onerror = () => {
      markCoverFailed(resolvedSrc);
      resolve();
    };

    image.src = resolvedSrc;
  }).finally(() => {
    pendingCoverWarmups.delete(resolvedSrc);
  });

  pendingCoverWarmups.set(resolvedSrc, warmup);
  return warmup;
}

export function CoverImage({
  src,
  alt,
  className,
  imageClassName,
  compact = false,
  priority = false,
}: CoverImageProps) {
  const [failed, setFailed] = useState(false);
  const resolvedSrc = resolveApiUrl(src);
  const wasLoadedBefore = !!resolvedSrc && loadedCoverSrcCache.has(resolvedSrc);
  const hadFailedBefore = !!resolvedSrc && failedCoverSrcCache.has(resolvedSrc);

  useEffect(() => {
    if (!wasLoadedBefore) {
      setFailed(false);
    }
  }, [src, wasLoadedBefore]);

  useEffect(() => {
    if (!priority || !resolvedSrc || wasLoadedBefore || hadFailedBefore) {
      return;
    }

    void warmCoverImage(src);
  }, [hadFailedBefore, priority, resolvedSrc, src, wasLoadedBefore]);

  const showImage = !!resolvedSrc && !failed && !hadFailedBefore;

  return (
    <div
      className={cn(
        "flex items-center justify-center overflow-hidden rounded-[inherit] bg-surface-contrast text-muted-foreground",
        className,
      )}
    >
      {showImage ? (
        <img
          alt={alt}
          className={cn("h-full w-full object-cover", imageClassName)}
          decoding="async"
          fetchPriority={priority ? "high" : "auto"}
          loading={priority ? "eager" : "lazy"}
          src={resolvedSrc}
          onLoad={(event) => {
            markCoverLoaded(event.currentTarget.currentSrc || resolvedSrc);
          }}
          onError={() => {
            markCoverFailed(resolvedSrc);
            setFailed(true);
          }}
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-[radial-gradient(circle_at_top,_hsl(var(--accent)/0.18),_transparent_55%)]">
          <ImageOff className={cn("text-muted-foreground", compact ? "h-4 w-4" : "h-8 w-8")} />
          {!compact ? <span className="px-4 text-center text-[12px] text-muted-foreground">No artwork</span> : null}
        </div>
      )}
    </div>
  );
}
