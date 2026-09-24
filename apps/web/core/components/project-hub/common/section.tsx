/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useId } from "react";
// plane imports
import { cn } from "@plane/utils";

type Props = {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  as?: "h2" | "h3" | "h4";
};

/** Titled region; the heading labels the region for assistive tech. */
export function HubSection({ title, description, actions, children, className, as: Heading = "h3" }: Props) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={cn("flex flex-col gap-3", className)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <Heading id={headingId} className="text-body-sm-semibold text-primary">
            {title}
          </Heading>
          {description && <p className="text-body-xs-regular text-tertiary">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** Bordered card on layer-1 (layers stack on the page surface). */
export function HubCard({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-md border border-subtle bg-layer-1 p-3", className)}>{children}</div>;
}

/** Label/value pair list. */
export function HubMeta({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-body-xs-regular">
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-tertiary">{item.label}</dt>
          <dd className="min-w-0 break-words text-secondary">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
