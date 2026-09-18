import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type InputProps = InputHTMLAttributes<HTMLInputElement>;

/** shadcn-style text input primitive. */
export function Input({ className, type = "text", ...props }: InputProps) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-11 w-full rounded-md border border-[var(--color-line)] bg-white px-3 py-2 text-sm text-[var(--color-ink)] shadow-sm transition-[color,box-shadow,border-color]",
        "placeholder:text-[var(--color-muted)]",
        "hover:border-[var(--color-muted)]",
        "focus-visible:border-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/30",
        "disabled:cursor-not-allowed disabled:bg-[var(--color-cream)] disabled:opacity-60",
        "read-only:bg-[var(--color-cream)] read-only:text-[var(--color-muted)]",
        "aria-[invalid=true]:border-[var(--color-danger)] aria-[invalid=true]:ring-[var(--color-danger)]/20",
        className,
      )}
      {...props}
    />
  );
}
