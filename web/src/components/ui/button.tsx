import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "quiet";

const styles: Record<Variant, string> = {
  primary: "bg-ink text-canvas hover:opacity-90",
  ghost: "bg-card text-ink shadow-[var(--shadow-card)] hover:bg-well",
  quiet: "text-muted hover:bg-well hover:text-ink",
};

export function Button({ variant = "ghost", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${styles[variant]} ${className}`}
      {...props}
    />
  );
}
