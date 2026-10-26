import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "quiet";

const styles: Record<Variant, string> = {
  primary: "bg-ink text-paper hover:bg-ink-soft",
  ghost: "border border-line bg-surface text-ink hover:bg-sunken",
  quiet: "text-muted hover:bg-sunken hover:text-ink",
};

export function Button({ variant = "ghost", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${styles[variant]} ${className}`}
      {...props}
    />
  );
}
