/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { CopyOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";
import { useTranslation } from "@plane/i18n";
import { copyTextToClipboard } from "@plane/utils";

type Props = { text: string; label?: string; successMessage?: string };

export function HubCopyButton({ text, label, successMessage }: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="secondary"
      size="sm"
      stretch="auto"
      icon={<Icon icon={CopyOutline} />}
      label={copied ? t("project_hub.common.copied") : (label ?? t("project_hub.common.copy"))}
      onClick={() => {
        void (async () => {
          await copyTextToClipboard(text);
          setCopied(true);
          setToast({ type: "success", title: successMessage ?? t("project_hub.common.copied") });
          setTimeout(() => setCopied(false), 2000);
        })();
      }}
    />
  );
}

/** Monospace command/token block that can be copied. */
export function HubCodeBlock({
  value,
  copyLabel,
  successMessage,
}: {
  value: string;
  copyLabel?: string;
  successMessage?: string;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <code className="font-mono min-w-0 flex-1 overflow-x-auto rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-xs-regular break-all whitespace-pre-wrap text-primary">
        {value}
      </code>
      <HubCopyButton text={value} label={copyLabel} successMessage={successMessage} />
    </div>
  );
}
