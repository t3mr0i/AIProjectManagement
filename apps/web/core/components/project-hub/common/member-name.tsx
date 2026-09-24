/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// hooks
import { useMember } from "@/hooks/store/use-member";

/** Display name of a native Plane member (ids stay native user ids). */
export const HubMemberName = observer(function HubMemberName({ userId }: { userId: string | null | undefined }) {
  const { t } = useTranslation();
  const { getUserDetails } = useMember();
  if (!userId) return <span>{t("project_hub.common.unknown")}</span>;
  const user = getUserDetails(userId);
  return <span>{user?.display_name || user?.first_name || t("project_hub.common.member")}</span>;
});

export const useMemberDisplayName = () => {
  const { t } = useTranslation();
  const { getUserDetails } = useMember();
  return (userId: string | null | undefined) => {
    if (!userId) return t("project_hub.common.unknown");
    const user = getUserDetails(userId);
    return user?.display_name || user?.first_name || t("project_hub.common.member");
  };
};
