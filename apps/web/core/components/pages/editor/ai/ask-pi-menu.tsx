/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { CircleArrowUp } from "lucide-react";
import { AiStar1Outline, CornerRightDownOutline, RefreshOutline } from "@makeplane/propel/icons";
// ui
import { Tooltip } from "@makeplane/propel/components/tooltip";
// components
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
import { RichTextEditor } from "@/components/editor/rich-text";
// helpers
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";

type Props = {
  /** Sends the instruction (applied to the current selection); the answer streams into `streamingText`. */
  handleAsk: (query: string) => Promise<void>;
  handleInsertText: (insertOnNextLine: boolean) => void;
  handleRegenerate: () => Promise<void>;
  isRegenerating: boolean;
  response: string | undefined;
  /** Partial answer while streaming; `undefined` when no request is running. */
  streamingText?: string;
  error?: string;
  workspaceSlug: string;
};

export function AskPiMenu(props: Props) {
  const {
    handleAsk,
    handleInsertText,
    handleRegenerate,
    isRegenerating,
    response,
    streamingText,
    error,
    workspaceSlug,
  } = props;
  const { t } = useTranslation();
  // states
  const [query, setQuery] = useState("");
  const isStreaming = streamingText !== undefined;
  const submit = () => {
    if (!query.trim() || isStreaming) return;
    void handleAsk(query);
  };
  // store hooks
  const { getWorkspaceBySlug } = useWorkspace();
  // derived values
  const workspaceId = getWorkspaceBySlug(workspaceSlug)?.id ?? "";

  return (
    <>
      <div
        className={cn("flex items-center gap-3 px-4 py-3.5", {
          "items-start": response,
        })}
      >
        <span className="grid size-7 flex-shrink-0 place-items-center rounded-full border border-subtle text-secondary">
          <AiStar1Outline className="size-3" />
        </span>
        {response ? (
          <div>
            <RichTextEditor
              // re-mount per answer: the read-only editor only reads `initialValue` once
              key={response}
              editable={false}
              displayConfig={{
                fontSize: "small-font",
              }}
              id="editor-ai-response"
              initialValue={response}
              containerClassName="!p-0 border-none"
              editorClassName="!pl-0"
              workspaceId={workspaceId}
              workspaceSlug={workspaceSlug}
            />
            <div className="mt-3 flex items-center gap-4">
              <button
                type="button"
                className="rounded-sm p-1 text-13 font-medium text-tertiary outline-none hover:bg-layer-1"
                onClick={() => handleInsertText(false)}
              >
                Replace selection
              </button>
              <Tooltip label="Add to next line">
                <button
                  type="button"
                  className="grid size-6 flex-shrink-0 place-items-center rounded-sm outline-none hover:bg-layer-1"
                  onClick={() => handleInsertText(true)}
                >
                  <CornerRightDownOutline className="size-4 text-tertiary" />
                </button>
              </Tooltip>
              <Tooltip label="Re-generate response">
                <button
                  type="button"
                  className="grid size-6 flex-shrink-0 place-items-center rounded-sm outline-none hover:bg-layer-1"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleRegenerate();
                  }}
                  disabled={isRegenerating}
                >
                  <RefreshOutline
                    className={cn("size-4 text-tertiary", {
                      "animate-spin": isRegenerating,
                    })}
                  />
                </button>
              </Tooltip>
            </div>
          </div>
        ) : isStreaming ? (
          <p aria-live="polite" className="text-13 whitespace-pre-wrap text-secondary">
            {streamingText || "AI is answering..."}
          </p>
        ) : error ? (
          <p role="alert" className="text-13 text-danger-primary">
            {error}
          </p>
        ) : (
          <p className="text-13 text-tertiary">{t("project_hub.ai.assist.title")}</p>
        )}
      </div>
      <div className="px-4 py-3">
        <form
          className="flex items-center gap-2 rounded-md border border-subtle p-2"
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            submit();
          }}
        >
          <span className="grid size-3 flex-shrink-0 place-items-center">
            <AiStar1Outline className="size-3 text-secondary" />
          </span>
          <input
            type="text"
            className="w-full border-none bg-transparent text-13 outline-none placeholder:text-placeholder"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tell AI what to do..."
            aria-label={t("project_hub.ai.assist.instruction")}
            disabled={isStreaming}
          />
          <button
            type="submit"
            aria-label={t("project_hub.ai.ask.submit")}
            disabled={!query.trim() || isStreaming}
            className="grid size-4 flex-shrink-0 place-items-center disabled:opacity-50"
          >
            <CircleArrowUp className="size-4 text-secondary" />
          </button>
        </form>
      </div>
    </>
  );
}
