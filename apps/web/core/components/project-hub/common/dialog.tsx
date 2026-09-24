/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FormEvent, ReactNode } from "react";
// plane imports
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  actions: ReactNode;
  onSubmit?: () => void;
  /** Blocks closing while a server request is in flight. */
  isBusy?: boolean;
};

/** Modal on the shared propel Dialog (same structure as native Plane modals). */
export function HubDialog({ isOpen, onClose, title, children, actions, onSubmit, isBusy }: Props) {
  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !isBusy) onClose();
      }}
      disablePointerDismissal
    >
      <DialogContent size="md">
        <form
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            onSubmit?.();
          }}
        >
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>{title}</DialogTitle>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="flex flex-col gap-3">{children}</div>
            </DialogBody>
          </DialogMain>
          <DialogActions>{actions}</DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
