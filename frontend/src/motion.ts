import type { Variants } from "motion/react";

export const motionTimings = {
  quick: { duration: 0.18, ease: [0.2, 0.75, 0.25, 1] as const },
  reveal: { duration: 0.42, ease: [0.2, 0.75, 0.25, 1] as const },
  spring: { type: "spring", stiffness: 280, damping: 26 } as const,
  marker: { type: "spring", stiffness: 420, damping: 24 } as const,
};

export const revealVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: motionTimings.reveal },
};

export const railVariants: Variants = {
  hidden: { opacity: 0, x: -16 },
  visible: { opacity: 1, x: 0, transition: motionTimings.reveal },
};

export const mainVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { ...motionTimings.reveal, delay: 0.14 } },
};

export const contentVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { ...motionTimings.reveal, delayChildren: 0.12, staggerChildren: 0.08 },
  },
};

export const selectionTransition = { duration: 0.28, ease: [0.2, 0.75, 0.25, 1] as const };

export const quoteVariants: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0, transition: motionTimings.spring },
  exit: { opacity: 0, y: -8, transition: motionTimings.quick },
};
