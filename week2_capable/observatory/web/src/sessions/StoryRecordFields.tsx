import { FileJson2 } from "lucide-react";
import { useState } from "react";
import type {
  SessionEvidenceRecord,
  SessionRecordFields as RecordFields,
} from "../contracts";
import styles from "./SessionStory.module.css";

function cx(...names: string[]): string {
  return names.map((name) => styles[name]).filter(Boolean).join(" ");
}

const notCaptured: Record<string, string> = {
  model_request_body_not_retained:
    "The exact assembled model request body was not retained for this "
    + "historical run.",
  provider_response_body_not_retained:
    "The exact provider response body was not retained for this historical "
    + "run.",
};

type Props = {
  record: SessionEvidenceRecord;
  sessionId: string;
  children: (detail: RecordFields) => React.ReactNode;
};

export function StoryRecordFields({ record, sessionId, children }: Props) {
  const [detail, setDetail] = useState<RecordFields | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const gap = record.capture_gaps.find((kind) => kind in notCaptured);

  const load = (): void => {
    setLoading(true);
    setError("");
    fetch(
      `/api/sessions/${encodeURIComponent(sessionId)}/records/`
      + `${encodeURIComponent(record.id)}/fields`,
      { cache: "no-store" },
    )
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json() as { detail?: string };
          throw new Error(
            payload.detail ?? `Record body unavailable (${response.status})`,
          );
        }
        return await response.json() as RecordFields;
      })
      .then(setDetail)
      .catch((reason: unknown) => {
        setError(
          reason instanceof Error ? reason.message : "Record body unavailable",
        );
      })
      .finally(() => setLoading(false));
  };

  if (gap !== undefined) {
    return (
      <div className={cx("story-availability", "is-redacted")}>
        {notCaptured[gap]}
      </div>
    );
  }

  if (detail === null) {
    return (
      <div className={cx("story-wire-load")}>
        <button disabled={loading} type="button" onClick={load}>
          <FileJson2 size={15} />
          {loading ? "Loading the exact body…" : "Open the exact body"}
        </button>
        {error ? <p role="alert">{error}</p> : null}
      </div>
    );
  }

  return <>{children(detail)}</>;
}
