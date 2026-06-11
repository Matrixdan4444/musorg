import { motion } from "framer-motion";
import { CircleHelp } from "lucide-react";
import { type CSSProperties, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";

const TOOLTIP_WIDTH = 280;
const VIEWPORT_MARGIN = 12;
const TOOLTIP_GAP = 14;
const ARROW_SIZE = 10;
const ARROW_INSET = 20;
const OPEN_SPACE_MIN = 110;
const CLOSE_DELAY_MS = 120;

interface TooltipPosition {
  top: number;
  left: number;
  anchorX: number;
  placement: "top" | "bottom";
}

export function FieldHelp({
  label,
  description,
  className,
}: {
  label: string;
  description: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const tooltipId = useId();

  const clearCloseTimer = () => {
    if (closeTimerRef.current != null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const showTooltip = () => {
    clearCloseTimer();
    setOpen(true);
  };

  const scheduleClose = () => {
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setOpen(false);
      closeTimerRef.current = null;
    }, CLOSE_DELAY_MS);
  };

  useLayoutEffect(() => {
    if (!open || typeof window === "undefined") {
      return;
    }

    const updatePosition = () => {
      const triggerRect = triggerRef.current?.getBoundingClientRect();
      const labelRect = triggerRef.current?.parentElement?.getBoundingClientRect();
      if (!triggerRect || !labelRect) {
        return;
      }

      const anchorX = triggerRect.left + triggerRect.width / 2;
      const left = Math.min(
        Math.max(anchorX - TOOLTIP_WIDTH / 2, VIEWPORT_MARGIN),
        window.innerWidth - TOOLTIP_WIDTH - VIEWPORT_MARGIN,
      );
      const placeAbove = labelRect.top >= OPEN_SPACE_MIN;

      setPosition({
        anchorX,
        left,
        top: placeAbove ? labelRect.top - TOOLTIP_GAP : labelRect.bottom + TOOLTIP_GAP,
        placement: placeAbove ? "top" : "bottom",
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => () => clearCloseTimer(), []);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open]);

  const tooltipStyle = position
    ? ({
        left: position.left,
        top: position.top,
        width: TOOLTIP_WIDTH,
      } satisfies CSSProperties)
    : undefined;
  const arrowLeft = position ? Math.min(Math.max(position.anchorX - position.left, ARROW_INSET), TOOLTIP_WIDTH - ARROW_INSET) : TOOLTIP_WIDTH / 2;

  return (
    <>
      <button
        ref={triggerRef}
        aria-describedby={open ? tooltipId : undefined}
        aria-label={label}
        className={cn(
          "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-muted-foreground/80 transition duration-150 hover:text-[hsl(var(--text-strong))] focus-visible:text-[hsl(var(--text-strong))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring)/0.2)]",
          className,
        )}
        type="button"
        onBlur={() => setOpen(false)}
        onFocus={showTooltip}
        onMouseEnter={showTooltip}
        onMouseLeave={scheduleClose}
      >
        <CircleHelp className="h-3.5 w-3.5" strokeWidth={1.8} />
      </button>
      {open && position && typeof document !== "undefined"
        ? createPortal(
            <motion.div
              className="fixed z-[90]"
              style={tooltipStyle ?? {}}
              initial={{
                opacity: 0,
                y: position.placement === "top" ? 10 : -10,
              }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              onMouseEnter={showTooltip}
              onMouseLeave={scheduleClose}
            >
              <motion.div
                id={tooltipId}
                role="tooltip"
                initial={{
                  opacity: 0,
                  scale: 0.97,
                  y: position.placement === "top" ? 4 : -4,
                }}
                animate={{
                  opacity: 1,
                  scale: 1,
                  y: position.placement === "top" ? "-100%" : 0,
                }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="app-tooltip-surface pointer-events-auto relative rounded-2xl px-3.5 py-2.5 text-[12px] leading-5 text-[hsl(var(--text-base))] backdrop-blur-md"
                style={{
                  transformOrigin: position.placement === "top" ? "bottom center" : "top center",
                }}
                onMouseDown={(event) => event.preventDefault()}
              >
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute h-[10px] w-[10px] rotate-45 rounded-[2px] border app-tooltip-surface"
                  style={{
                    left: arrowLeft - ARROW_SIZE / 2,
                    top: position.placement === "top" ? undefined : -ARROW_SIZE / 2,
                    bottom: position.placement === "top" ? -ARROW_SIZE / 2 : undefined,
                    borderLeftColor: position.placement === "top" ? "transparent" : undefined,
                    borderTopColor: position.placement === "top" ? "transparent" : undefined,
                    borderRightColor: position.placement === "bottom" ? "transparent" : undefined,
                    borderBottomColor: position.placement === "bottom" ? "transparent" : undefined,
                  }}
                />
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute left-0 right-0 h-6"
                  style={{
                    top: position.placement === "top" ? "100%" : undefined,
                    bottom: position.placement === "bottom" ? "100%" : undefined,
                  }}
                />
                {description}
              </motion.div>
            </motion.div>,
            document.body,
          )
        : null}
    </>
  );
}
