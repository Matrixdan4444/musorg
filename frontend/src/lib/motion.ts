import { useReducedMotion, type Transition, type Variants } from "framer-motion";

export const easeApple = [0.22, 1, 0.36, 1] as const;

export const springSnappy: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 34,
  mass: 0.7,
};

export const springSoft: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 30,
  mass: 0.9,
};

export const durations = {
  micro: 0.16,
  base: 0.22,
} as const;

const instant: Transition = { duration: 0 };

const modalVariants: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1 },
};

const modalVariantsReduced: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
};

const overlayVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
};

/**
 * Motion presets that gracefully collapse to instant transitions when the user
 * has "Reduce motion" enabled. Use in modals, navigation and transitions so the
 * whole app honours the OS accessibility setting from a single place.
 */
export function useAppMotion() {
  const reduced = useReducedMotion();
  return {
    reduced: Boolean(reduced),
    spring: reduced ? instant : springSnappy,
    springSoft: reduced ? instant : springSoft,
    tap: reduced ? {} : { scale: 0.97 },
    modalVariants: reduced ? modalVariantsReduced : modalVariants,
    overlayVariants,
    modalTransition: reduced ? instant : springSnappy,
    overlayTransition: reduced ? instant : { duration: durations.micro, ease: easeApple },
  };
}
