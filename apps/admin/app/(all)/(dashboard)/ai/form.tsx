/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useForm } from "react-hook-form";
import { Button } from "@makeplane/propel/components/button";
import { Select, SelectContent, SelectItem, SelectList, SelectTrigger } from "@makeplane/propel/components/select";
import type { IFormattedInstanceConfiguration, TInstanceAIConfigurationKeys } from "@plane/types";
// components
import type { TControllerInputFormField } from "@/components/common/controller-input";
import { ControllerInput } from "@/components/common/controller-input";
import { setToast } from "@plane/blocks/toast";
// hooks
import { useInstance } from "@/hooks/store";

type IInstanceAIForm = {
  config: IFormattedInstanceConfiguration;
};

type AIFormValues = Record<TInstanceAIConfigurationKeys, string>;

type TLLMProvider = "openai" | "anthropic" | "gemini" | "ollama" | "openai_compatible";

type TProviderPreset = {
  label: string;
  /** Model used when `LLM_MODEL` is empty. */
  defaultModel: string;
  keyPlaceholder: string;
  keyRequired: boolean;
  baseUrlPlaceholder: string;
  baseUrlRequired: boolean;
  docsUrl?: string;
};

const PROVIDERS: Record<TLLMProvider, TProviderPreset> = {
  openai: {
    label: "OpenAI",
    defaultModel: "gpt-4o-mini",
    keyPlaceholder: "sk-…",
    keyRequired: true,
    baseUrlPlaceholder: "https://api.openai.com/v1",
    baseUrlRequired: false,
    docsUrl: "https://platform.openai.com/docs/models",
  },
  anthropic: {
    label: "Anthropic",
    defaultModel: "claude-opus-5",
    keyPlaceholder: "sk-ant-…",
    keyRequired: true,
    baseUrlPlaceholder: "https://api.anthropic.com",
    baseUrlRequired: false,
    docsUrl: "https://docs.anthropic.com/en/docs/about-claude/models",
  },
  gemini: {
    label: "Google Gemini",
    defaultModel: "gemini-2.5-flash",
    keyPlaceholder: "AIza…",
    keyRequired: true,
    baseUrlPlaceholder: "https://generativelanguage.googleapis.com",
    baseUrlRequired: false,
    docsUrl: "https://ai.google.dev/gemini-api/docs/models",
  },
  ollama: {
    label: "Ollama (self-hosted)",
    defaultModel: "llama3.1",
    keyPlaceholder: "Not needed for a local Ollama",
    keyRequired: false,
    baseUrlPlaceholder: "http://localhost:11434",
    baseUrlRequired: false,
    docsUrl: "https://ollama.com/library",
  },
  openai_compatible: {
    label: "OpenAI-compatible endpoint",
    defaultModel: "",
    keyPlaceholder: "API key of your endpoint",
    keyRequired: false,
    baseUrlPlaceholder: "https://llm.example.com/v1",
    baseUrlRequired: true,
  },
};

const isProvider = (value: string | undefined): value is TLLMProvider => !!value && value in PROVIDERS;

export function InstanceAIForm(props: IInstanceAIForm) {
  const { config } = props;
  // store
  const { updateInstanceConfigurations } = useInstance();
  // form data
  const {
    handleSubmit,
    control,
    watch,
    setValue,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<AIFormValues>({
    defaultValues: {
      LLM_PROVIDER: isProvider(config["LLM_PROVIDER"]) ? config["LLM_PROVIDER"] : "openai",
      LLM_API_KEY: config["LLM_API_KEY"],
      LLM_MODEL: config["LLM_MODEL"],
      LLM_BASE_URL: config["LLM_BASE_URL"],
      LLM_EMBEDDING_MODEL: config["LLM_EMBEDDING_MODEL"],
    },
  });

  const providerKey = watch("LLM_PROVIDER");
  const provider = PROVIDERS[isProvider(providerKey) ? providerKey : "openai"];

  const aiFormFields: TControllerInputFormField<AIFormValues>[] = [
    {
      key: "LLM_MODEL",
      type: "text",
      label: "Model",
      description: (
        <>
          {provider.defaultModel
            ? `Leave empty to use the ${provider.label} default (${provider.defaultModel}).`
            : "The model name your endpoint serves."}{" "}
          {provider.docsUrl && (
            <a
              href={provider.docsUrl}
              target="_blank"
              className="text-accent-primary hover:underline"
              rel="noreferrer"
              aria-label={`${provider.label} models documentation`}
            >
              Available models
            </a>
          )}
        </>
      ),
      placeholder: provider.defaultModel || "model-name",
      error: Boolean(errors.LLM_MODEL),
      required: !provider.defaultModel,
    },
    {
      key: "LLM_API_KEY",
      type: "password",
      label: "API key",
      description: provider.keyRequired
        ? `Your ${provider.label} API key. It is stored encrypted and never shown to workspace members.`
        : "Optional for this provider. Stored encrypted when set.",
      placeholder: provider.keyPlaceholder,
      error: Boolean(errors.LLM_API_KEY),
      required: false,
    },
    {
      key: "LLM_BASE_URL",
      type: "text",
      label: "Base URL",
      description: provider.baseUrlRequired
        ? "Required: the OpenAI-compatible endpoint (e.g. vLLM, LM Studio, Azure OpenAI, LiteLLM)."
        : "Optional. Leave empty for the provider's default endpoint, or set a proxy / self-hosted URL.",
      placeholder: provider.baseUrlPlaceholder,
      error: Boolean(errors.LLM_BASE_URL),
      required: provider.baseUrlRequired,
    },
    {
      key: "LLM_EMBEDDING_MODEL",
      type: "text",
      label: "Embedding model",
      description:
        "Optional. Enables semantic search for Ask AI and proposals. Leave empty for the provider default; providers without embeddings fall back to keyword search.",
      placeholder: "text-embedding-3-small",
      error: Boolean(errors.LLM_EMBEDDING_MODEL),
      required: false,
    },
  ];

  const onSubmit = async (formData: AIFormValues) => {
    const payload: Partial<AIFormValues> = { ...formData };

    await updateInstanceConfigurations(payload)
      .then(() =>
        setToast({
          type: "success",
          title: "Success",
          message: "AI settings updated successfully",
        })
      )
      .catch((err) => console.error(err));
  };

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <div>
          <div className="pb-1 text-18 font-medium text-primary">Language model</div>
          <div className="text-13 font-regular text-tertiary">
            One provider powers every AI feature: Ask AI, brief proposals, status reports and writing help. Without a
            configured model the AI runs in rule-based mode.
          </div>
        </div>
        <div className="grid-col grid w-full grid-cols-1 items-start justify-between gap-x-12 gap-y-8 lg:grid-cols-3">
          <div className="flex flex-col gap-1">
            <h4 className="text-13 text-tertiary">Provider</h4>
            <Select
              items={Object.fromEntries(Object.entries(PROVIDERS).map(([key, value]) => [key, value.label]))}
              value={isProvider(providerKey) ? providerKey : "openai"}
              onValueChange={(value) => setValue("LLM_PROVIDER", String(value), { shouldDirty: true })}
            >
              <SelectTrigger size="lg" placeholder="Select a provider" />
              <SelectContent>
                <SelectList>
                  {Object.entries(PROVIDERS).map(([key, value]) => (
                    <SelectItem key={key} value={key} label={value.label} size="lg" />
                  ))}
                </SelectList>
              </SelectContent>
            </Select>
            <p className="text-11 text-tertiary">
              OpenAI, Anthropic, Google Gemini, a local Ollama or any OpenAI-compatible endpoint.
            </p>
          </div>
          {aiFormFields.map((field) => (
            <ControllerInput
              key={field.key}
              control={control}
              type={field.type}
              name={field.key}
              label={field.label}
              description={field.description}
              placeholder={field.placeholder}
              error={field.error}
              required={field.required}
            />
          ))}
        </div>
      </div>

      <div className="flex flex-col items-start gap-4">
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          onClick={handleSubmit(onSubmit)}
          loading={isSubmitting}
          disabled={!isDirty}
          label={isSubmitting ? "Saving" : "Save changes"}
        />
      </div>
    </div>
  );
}
