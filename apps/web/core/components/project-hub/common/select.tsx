/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useId } from "react";
// plane imports
import { Select } from "@plane/blocks/select";

export type THubOption = { value: string; label: string };

type Props = {
  label: string;
  value: string | null | undefined;
  options: THubOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  hideLabel?: boolean;
};

/** Labelled single select on top of the shared `@plane/blocks/select`. */
export function HubSelect({ label, value, options, onChange, disabled, placeholder, hideLabel }: Props) {
  const id = useId();
  const selected = options.find((o) => o.value === value) ?? null;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className={hideLabel ? "sr-only" : "text-caption-md-medium text-tertiary"}>
        {label}
      </label>
      <Select<THubOption>
        getValues={() => options}
        value={selected}
        onChange={(val) => onChange(val)}
        getOptionValue={(o) => o.value}
        getOptionLabel={(o) => o.label}
        showSearch={options.length > 8}
        pinSelected={false}
        disabled={disabled}
      >
        <Select.Trigger id={id} variant="select-md" disabled={disabled}>
          {selected?.label ?? placeholder ?? label}
        </Select.Trigger>
      </Select>
    </div>
  );
}
