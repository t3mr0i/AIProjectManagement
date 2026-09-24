/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId } from "react";
// plane imports
import { Input } from "@makeplane/propel/components/input";
import { TextArea } from "@makeplane/propel/components/text-area";

type TBase = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  hint?: string;
  required?: boolean;
  hideLabel?: boolean;
};

/** Labelled text input (explicit <label for>, hint linked via aria-describedby). */
export function HubTextField({
  label,
  value,
  onChange,
  placeholder,
  disabled,
  hint,
  required,
  hideLabel,
  type = "text",
}: TBase & { type?: "text" | "number" | "date" | "url" | "password" | "datetime-local" }) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={hideLabel ? "sr-only" : "text-caption-md-medium text-tertiary"}>
        {label}
      </label>
      <Input
        id={id}
        size="md"
        type={type}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && (
        <p id={hintId} className="text-caption-sm-regular text-tertiary">
          {hint}
        </p>
      )}
    </div>
  );
}

/** Labelled multi-line field. */
export function HubTextAreaField({ label, value, onChange, placeholder, disabled, hint, required, hideLabel }: TBase) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={hideLabel ? "sr-only" : "text-caption-md-medium text-tertiary"}>
        {label}
      </label>
      <TextArea
        id={id}
        size="md"
        surface="field"
        autoResize
        maxRows={12}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && (
        <p id={hintId} className="text-caption-sm-regular text-tertiary">
          {hint}
        </p>
      )}
    </div>
  );
}
