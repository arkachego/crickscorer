import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type AlertProps = {
  tone?: "error" | "info";
  title?: string;
  children: ReactNode;
  className?: string;
  role?: "alert" | "status";
};

export function Alert({
  tone = "info",
  title,
  children,
  className,
  role = "alert",
}: AlertProps) {
  return (
    <div
      role={role}
      aria-label={title}
      className={cn(
        "rounded-md border px-4 py-3 text-sm",
        tone === "error" &&
          "border-red-200 bg-red-50 text-[var(--color-danger)]",
        tone === "info" &&
          "border-[var(--color-line)] bg-white text-[var(--color-ink)]",
        className,
      )}
    >
      {title ? <p className="mb-1 font-semibold">{title}</p> : null}
      <div>{children}</div>
    </div>
  );
}
