import { cn } from "@/lib/cn";

interface BrandLogoProps {
  className?: string;
}

export function BrandLogo({ className }: BrandLogoProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-[12px] bg-[#1b1b1f]",
        className,
      )}
    >
      <svg
        viewBox="0 0 94 40"
        className="w-3/4"
        role="img"
        aria-label="Musorg"
      >
        <defs>
          <linearGradient id="brandHills" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#f5a623" />
            <stop offset="0.5" stopColor="#d63d8f" />
            <stop offset="1" stopColor="#25b08a" />
          </linearGradient>
        </defs>
        <path
          d="M3,38 L3,24 Q15,8 27,22 Q39,36 51,18 Q63,4 75,22 Q85,30 91,20 L91,38 Z"
          fill="url(#brandHills)"
        />
      </svg>
    </div>
  );
}
