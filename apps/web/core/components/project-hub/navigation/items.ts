/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentType, SVGProps } from "react";
// plane imports
import {
  ActivityOutline,
  BriefsOutline,
  ChatOutline,
  LibraryOutline,
  OverviewOutline,
  SearchOutline,
  TimelineOutline,
} from "@makeplane/propel/icons";

type TGlyph = ComponentType<SVGProps<SVGSVGElement>>;

export type TProjectHubPage = { key: string; segment: string; i18nKey: string; icon: TGlyph };

/** Project tabs (PRD §11.2): Aktivität, Arbeit, Roadmap, Wissen. */
export const PROJECT_HUB_PROJECT_PAGES: TProjectHubPage[] = [
  { key: "hub_activity", segment: "activity", i18nKey: "project_hub.nav.activity", icon: ActivityOutline as TGlyph },
  { key: "hub_packages", segment: "packages", i18nKey: "project_hub.nav.packages", icon: BriefsOutline as TGlyph },
  { key: "hub_roadmap", segment: "roadmap", i18nKey: "project_hub.nav.roadmap", icon: TimelineOutline as TGlyph },
  { key: "hub_knowledge", segment: "knowledge", i18nKey: "project_hub.nav.knowledge", icon: LibraryOutline as TGlyph },
];

/** Workspace navigation (PRD §11.2): Übersicht, Nachrichten, Roadmap, Suche. */
export const PROJECT_HUB_WORKSPACE_PAGES: TProjectHubPage[] = [
  { key: "hub_overview", segment: "", i18nKey: "project_hub.nav.overview", icon: OverviewOutline as TGlyph },
  { key: "hub_messages", segment: "messages", i18nKey: "project_hub.nav.messages", icon: ChatOutline as TGlyph },
  { key: "hub_roadmap", segment: "roadmap", i18nKey: "project_hub.nav.roadmap", icon: TimelineOutline as TGlyph },
  { key: "hub_search", segment: "search", i18nKey: "project_hub.nav.search", icon: SearchOutline as TGlyph },
];
