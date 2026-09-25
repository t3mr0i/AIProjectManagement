/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, ReactNode, SVGProps } from "react";
import { useId } from "react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
// local imports
import { HubDialog } from "../common/dialog";
import { HubGroupBar, HubList } from "../common/list";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

/**
 * Settings section: title + one muted line, then the grouped card(s) (UI_GUIDELINES "Settings").
 * The heading labels the region for assistive tech.
 */
export function SettingsSection({
  title,
  description,
  actions,
  children,
  as: Heading = "h2",
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  /** Quiet action(s) on the right of the heading. */
  actions?: ReactNode;
  children: ReactNode;
  as?: "h2" | "h3";
  className?: string;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={cn("flex min-w-0 flex-col gap-3", className)}>
      <div className="flex min-w-0 items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <Heading id={headingId} className="text-body-sm-medium text-primary">
            {title}
          </Heading>
          {description && <p className="text-caption-md-regular text-tertiary">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** Rounded card holding grouped rows; optional subtle header bar with a muted count and trailing control. */
export function SettingsCard({
  title,
  icon,
  count,
  trailing,
  children,
  className,
  "aria-label": ariaLabel,
}: {
  title?: ReactNode;
  icon?: TGlyph;
  count?: number;
  trailing?: ReactNode;
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <HubList variant="card" aria-label={ariaLabel} className={className}>
      {title && <HubGroupBar title={title} icon={icon} count={count} trailing={trailing} sticky={false} />}
      {children}
    </HubList>
  );
}

/**
 * One settings row: `[icon] title / muted description ………… control`. 36px minimum, hairline
 * separators, nothing wraps (the description truncates).
 */
export function SettingsRow({
  icon: Glyph,
  title,
  description,
  control,
  disabled,
  indent,
  className,
}: {
  icon?: TGlyph;
  title: ReactNode;
  description?: ReactNode;
  control?: ReactNode;
  disabled?: boolean;
  /** Nested rows (e.g. projects under the workspace toggle). */
  indent?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-9 w-full min-w-0 items-center gap-3 border-b border-subtle py-1.5 pr-3 text-13 last:border-b-0",
        indent ? "pl-6" : "pl-3",
        disabled && "opacity-60",
        className
      )}
    >
      {Glyph && <Glyph className="size-4 shrink-0 text-tertiary" aria-hidden="true" />}
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-primary">{title}</span>
        {description && <span className="truncate text-caption-md-regular text-tertiary">{description}</span>}
      </div>
      {control && <div className="flex shrink-0 items-center gap-1.5">{control}</div>}
    </div>
  );
}

/** Quiet confirmation for destructive settings actions (revoke, deactivate, disconnect, apply). */
export function SettingsConfirmDialog({
  isOpen,
  title,
  description,
  confirmLabel,
  destructive = true,
  busy,
  onConfirm,
  onClose,
}: {
  isOpen: boolean;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <HubDialog
      isOpen={isOpen}
      onClose={onClose}
      isBusy={busy}
      title={title}
      onSubmit={onConfirm}
      actions={
        <>
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            label={t("project_hub.common.cancel")}
            onClick={onClose}
          />
          <Button
            type="submit"
            variant={destructive ? "danger" : "primary"}
            size="md"
            stretch="auto"
            loading={busy}
            label={confirmLabel}
          />
        </>
      }
    >
      {description && <p className="text-13 text-secondary">{description}</p>}
    </HubDialog>
  );
}
