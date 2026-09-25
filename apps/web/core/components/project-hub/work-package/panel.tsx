/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useId } from "react";
// plane imports
import { cn } from "@plane/utils";

type TSectionProps = {
  title: ReactNode;
  description?: ReactNode;
  /** Quiet actions on the right of the heading row. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  as?: "h2" | "h3" | "h4";
};

/**
 * Dense section inside the work package tabs (Linear detail density): a 13px medium heading with
 * an optional one-line muted description, actions on the right, 8px to the body. No frame.
 */
export function WpSection({ title, description, actions, children, className, as: Heading = "h3" }: TSectionProps) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={cn("flex min-w-0 flex-col gap-2", className)}>
      <div className="flex min-h-7 flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div className="flex min-w-0 flex-col">
          <Heading id={headingId} className="truncate text-13 font-medium text-primary">
            {title}
          </Heading>
          {description && <p className="text-caption-md-regular text-tertiary">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-1.5">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** Stack of `WpEntry`s separated by hairlines (never a card inside a card). */
export function WpEntryList({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("flex min-w-0 flex-col divide-y divide-subtle", className)}>{children}</div>;
}

/** One entry of a `WpEntryList`: compact vertical rhythm, 12px metadata, no border of its own. */
export function WpEntry({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("flex min-w-0 flex-col gap-1 py-2 first:pt-0 last:pb-0", className)}>{children}</div>;
}

/** One quiet muted line (12px) for secondary information under a heading or row. */
export function WpMutedLine({
  children,
  className,
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <p className={cn("min-w-0 truncate text-caption-md-regular text-tertiary", className)} title={title}>
      {children}
    </p>
  );
}
