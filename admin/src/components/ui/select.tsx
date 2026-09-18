import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

type SelectItemRecord = {
  textValue: string;
  content: ReactNode;
};

type SelectContextValue = {
  value?: string;
  open: boolean;
  disabled?: boolean;
  triggerId: string;
  listboxId: string;
  /** Bumps when the selected item’s label first becomes available. */
  labelTick: number;
  setOpen: (open: boolean) => void;
  onValueChange?: (value: string) => void;
  registerItem: (value: string, textValue: string, content: ReactNode) => void;
  getItem: (value: string) => SelectItemRecord | undefined;
};

const SelectContext = createContext<SelectContextValue | null>(null);

function useSelectContext(component: string): SelectContextValue {
  const ctx = useContext(SelectContext);
  if (!ctx) {
    throw new Error(`${component} must be used within <Select>`);
  }
  return ctx;
}

type SelectProps = {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  children: ReactNode;
};

export function Select({
  value,
  defaultValue,
  onValueChange,
  disabled,
  children,
}: SelectProps) {
  const reactId = useId();
  const [uncontrolled, setUncontrolled] = useState(defaultValue);
  const [open, setOpen] = useState(false);
  const [labelTick, setLabelTick] = useState(0);
  const itemsRef = useRef(new Map<string, SelectItemRecord>());
  const resolvedValue = value ?? uncontrolled;
  const resolvedValueRef = useRef(resolvedValue);
  resolvedValueRef.current = resolvedValue;

  const registerItem = useCallback(
    (itemValue: string, textValue: string, content: ReactNode) => {
      const prev = itemsRef.current.get(itemValue);
      itemsRef.current.set(itemValue, { textValue, content });
      // Re-render trigger once when the selected option’s label becomes known.
      if (
        itemValue === resolvedValueRef.current &&
        (!prev || prev.textValue !== textValue)
      ) {
        setLabelTick((tick) => tick + 1);
      }
    },
    [],
  );

  const getItem = useCallback(
    (itemValue: string) => itemsRef.current.get(itemValue),
    [],
  );

  const ctx = useMemo<SelectContextValue>(
    () => ({
      value: resolvedValue,
      open,
      disabled,
      triggerId: `${reactId}-trigger`,
      listboxId: `${reactId}-listbox`,
      labelTick,
      setOpen: (next) => {
        if (!disabled) setOpen(next);
      },
      onValueChange: (next) => {
        if (value === undefined) setUncontrolled(next);
        onValueChange?.(next);
      },
      registerItem,
      getItem,
    }),
    [
      disabled,
      getItem,
      labelTick,
      onValueChange,
      open,
      reactId,
      registerItem,
      resolvedValue,
      value,
    ],
  );

  return (
    <SelectContext.Provider value={ctx}>
      <div className="relative">{children}</div>
    </SelectContext.Provider>
  );
}

type SelectTriggerProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function SelectTrigger({
  className,
  children,
  id,
  ...props
}: SelectTriggerProps) {
  const ctx = useSelectContext("SelectTrigger");
  const rootRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!ctx.open) return;
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (rootRef.current?.parentElement?.contains(target)) return;
      ctx.setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") ctx.setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [ctx]);

  return (
    <button
      ref={rootRef}
      type="button"
      role="combobox"
      id={id ?? ctx.triggerId}
      aria-controls={ctx.listboxId}
      aria-expanded={ctx.open}
      aria-haspopup="listbox"
      disabled={ctx.disabled}
      className={cn(
        "flex h-11 w-full items-center justify-between gap-2 rounded-md border border-[var(--color-line)] bg-white px-3 py-2 text-left text-sm text-[var(--color-ink)] shadow-sm transition-[color,box-shadow,border-color]",
        "hover:border-[var(--color-muted)]",
        "focus-visible:border-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/30",
        "disabled:cursor-not-allowed disabled:bg-[var(--color-cream)] disabled:opacity-60",
        "aria-[invalid=true]:border-[var(--color-danger)]",
        className,
      )}
      onClick={() => ctx.setOpen(!ctx.open)}
      {...props}
    >
      {children}
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="size-4 shrink-0 text-[var(--color-muted)]"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </button>
  );
}

type SelectValueProps = {
  placeholder?: string;
  className?: string;
};

export function SelectValue({ placeholder, className }: SelectValueProps) {
  const ctx = useSelectContext("SelectValue");
  // labelTick ensures we re-read the registry after items mount.
  void ctx.labelTick;
  const item = ctx.value ? ctx.getItem(ctx.value) : undefined;
  const showPlaceholder = !item;

  return (
    <span
      className={cn(
        "flex min-w-0 flex-1 items-center",
        showPlaceholder && "text-[var(--color-muted)]",
        className,
      )}
      data-placeholder={showPlaceholder ? "" : undefined}
    >
      {item?.content ?? placeholder ?? "Select"}
    </span>
  );
}

type SelectContentProps = HTMLAttributes<HTMLDivElement>;

export function SelectContent({ className, children, ...props }: SelectContentProps) {
  const ctx = useSelectContext("SelectContent");

  // Keep items mounted while closed so option labels remain registered for SelectValue.
  if (!ctx.open) {
    return <div className="hidden">{children}</div>;
  }

  return (
    <div
      id={ctx.listboxId}
      role="listbox"
      className={cn(
        "absolute z-50 mt-1 max-h-72 w-full overflow-auto rounded-md border border-[var(--color-line)] bg-white p-1 text-[var(--color-ink)] shadow-md",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

type SelectItemProps = {
  value: string;
  /** Plain-text label used for accessibility / tests when children are rich nodes. */
  textValue?: string;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
};

export function SelectItem({
  value,
  textValue,
  children,
  disabled,
  className,
}: SelectItemProps) {
  const ctx = useSelectContext("SelectItem");
  const selected = ctx.value === value;
  const stringChild =
    typeof children === "string" || typeof children === "number"
      ? String(children)
      : undefined;
  const resolvedText = textValue ?? stringChild;
  const registryLabel = resolvedText ?? value;

  useLayoutEffect(() => {
    ctx.registerItem(value, registryLabel, children);
  }, [children, ctx.registerItem, registryLabel, value]);

  return (
    <div
      role={ctx.open ? "option" : undefined}
      aria-selected={ctx.open ? selected : undefined}
      aria-label={resolvedText}
      aria-disabled={disabled || undefined}
      data-disabled={disabled ? "" : undefined}
      data-value={value}
      className={cn(
        "relative flex w-full cursor-default items-center rounded-sm px-2 py-2 text-sm outline-none select-none",
        "hover:bg-[var(--color-cream)] hover:text-[var(--color-pitch-deep)]",
        "focus:bg-[var(--color-cream)] focus:text-[var(--color-pitch-deep)]",
        selected && "bg-[var(--color-cream)]",
        disabled && "pointer-events-none opacity-50",
        className,
      )}
      onMouseDown={(event) => {
        event.preventDefault();
      }}
      onClick={() => {
        if (disabled) return;
        ctx.onValueChange?.(value);
        ctx.setOpen(false);
      }}
    >
      <span className="flex min-w-0 flex-1 items-center">{children}</span>
    </div>
  );
}

export function SelectGroup({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-1", className)} {...props} />;
}

export function SelectLabel({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "px-2 py-1.5 text-xs font-semibold text-[var(--color-muted)]",
        className,
      )}
      {...props}
    />
  );
}

export function SelectSeparator({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("-mx-1 my-1 h-px bg-[var(--color-line)]", className)}
      {...props}
    />
  );
}
