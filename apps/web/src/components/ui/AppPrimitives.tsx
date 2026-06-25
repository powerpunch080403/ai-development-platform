import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

export type ActionMenuItem = {
  label: string;
  onSelect: () => void;
  destructive?: boolean;
};

type ActionMenuProps = {
  ariaLabel: string;
  items: ActionMenuItem[];
};

export function ActionMenu({ ariaLabel, items }: ActionMenuProps) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="menu-icon-button" aria-label={ariaLabel}>
          ⋯
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="app-dropdown-content" sideOffset={6} align="end">
          {items.map((item) => (
            <DropdownMenu.Item
              key={item.label}
              className={item.destructive ? "app-dropdown-item danger-action" : "app-dropdown-item"}
              onSelect={item.onSelect}
            >
              {item.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

type TextInputDialogProps = {
  open: boolean;
  title: string;
  description?: string;
  label: string;
  initialValue: string;
  confirmLabel?: string;
  onOpenChange: (open: boolean) => void;
  onSubmit: (value: string) => void | Promise<void>;
};

export function TextInputDialog({
  open,
  title,
  description,
  label,
  initialValue,
  confirmLabel = "저장",
  onOpenChange,
  onSubmit,
}: TextInputDialogProps) {
  const [value, setValue] = useState(initialValue);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) setValue(initialValue);
  }, [initialValue, open]);

  async function submit() {
    const nextValue = value.trim();
    if (!nextValue || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(nextValue);
      onOpenChange(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="app-dialog-overlay" />
        <Dialog.Content className="app-dialog-content">
          <Dialog.Title className="app-dialog-title">{title}</Dialog.Title>
          {description && <Dialog.Description className="app-dialog-description">{description}</Dialog.Description>}
          <label className="app-dialog-field">
            {label}
            <input
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void submit();
              }}
              autoFocus
            />
          </label>
          <div className="app-dialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="secondary" disabled={submitting}>
                취소
              </button>
            </Dialog.Close>
            <button type="button" onClick={() => void submit()} disabled={!value.trim() || submitting}>
              {submitting ? "저장 중" : confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  destructive?: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void | Promise<void>;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "확인",
  destructive = false,
  onOpenChange,
  onConfirm,
}: ConfirmDialogProps) {
  const [submitting, setSubmitting] = useState(false);

  async function confirm() {
    if (submitting) return;
    setSubmitting(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="app-dialog-overlay" />
        <Dialog.Content className="app-dialog-content">
          <Dialog.Title className="app-dialog-title">{title}</Dialog.Title>
          <Dialog.Description className="app-dialog-description">{description}</Dialog.Description>
          <div className="app-dialog-actions">
            <Dialog.Close asChild>
              <button type="button" className="secondary" disabled={submitting}>
                취소
              </button>
            </Dialog.Close>
            <button
              type="button"
              className={destructive ? "danger-button" : undefined}
              onClick={() => void confirm()}
              disabled={submitting}
            >
              {submitting ? "처리 중" : confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
