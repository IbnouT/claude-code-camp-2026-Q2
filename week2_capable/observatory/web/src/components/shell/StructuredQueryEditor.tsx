import type { QueryScope } from "../../data/ask";
import {
  filterFields,
  filterOperators,
  type QueryOrder,
} from "./queryOptions";

type Props = {
  scope: QueryScope;
  enabled: boolean;
  field: string;
  operator: string;
  value: string;
  order: QueryOrder;
  valid: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onFieldChange: (field: string) => void;
  onOperatorChange: (operator: string) => void;
  onValueChange: (value: string) => void;
  onOrderChange: (order: QueryOrder) => void;
};

export function StructuredQueryEditor({
  scope,
  enabled,
  field,
  operator,
  value,
  order,
  valid,
  onEnabledChange,
  onFieldChange,
  onOperatorChange,
  onValueChange,
  onOrderChange,
}: Props) {
  return (
    <details className="structured-query">
      <summary>Structured search</summary>
      <label className="structured-toggle">
        <input
          checked={enabled}
          type="checkbox"
          onChange={(event) => onEnabledChange(event.target.checked)}
        />
        <span>Use an exact typed evidence query</span>
      </label>
      <div className="structured-controls">
        <label>
          <span>Field</span>
          <select
            aria-label="Evidence field"
            disabled={!enabled}
            value={field}
            onChange={(event) => onFieldChange(event.target.value)}
          >
            {filterFields(scope.space).map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Match</span>
          <select
            aria-label="Filter operator"
            disabled={!enabled}
            value={operator}
            onChange={(event) => onOperatorChange(event.target.value)}
          >
            {filterOperators(field).map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Value</span>
          <input
            aria-label="Filter value"
            disabled={!enabled}
            value={value}
            onChange={(event) => onValueChange(event.target.value)}
          />
        </label>
        <label>
          <span>Order</span>
          <select
            aria-label="Result order"
            disabled={!enabled}
            value={order}
            onChange={(event) => {
              onOrderChange(event.target.value as QueryOrder);
            }}
          >
            <option value="causal">causal</option>
            <option value="chronological">chronological</option>
            <option value="cost_desc">highest cost</option>
          </select>
        </label>
      </div>
      {!valid ? (
        <p className="structured-error">Cost must be a number.</p>
      ) : null}
    </details>
  );
}
