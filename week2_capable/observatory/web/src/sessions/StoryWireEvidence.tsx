import { FileJson2 } from "lucide-react";
import { useState } from "react";
import type {
  SessionEvidenceRecord,
  SessionWireEvidence,
} from "../contracts";
import styles from "./SessionStory.module.css";

function cx(...names: string[]): string {
  return names.map((name) => styles[name]).filter(Boolean).join(" ");
}

type Props = {
  record: SessionEvidenceRecord;
  sessionId: string;
};

export function StoryWireEvidence({ record, sessionId }: Props) {
  const [detail, setDetail] = useState<SessionWireEvidence | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const redacted = record.fields.redacted === true;

  const load = (): void => {
    setLoading(true);
    setError("");
    fetch(
      `/api/sessions/${encodeURIComponent(sessionId)}/wire/${record.sequence}`,
      { cache: "no-store" },
    )
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json() as { detail?: string };
          throw new Error(
            payload.detail ?? `Wire evidence unavailable (${response.status})`,
          );
        }
        return await response.json() as SessionWireEvidence;
      })
      .then(setDetail)
      .catch((reason: unknown) => {
        setError(
          reason instanceof Error ? reason.message : "Wire evidence unavailable",
        );
      })
      .finally(() => setLoading(false));
  };

  if (redacted) {
    return (
      <div className={cx("story-availability", "is-redacted")}>
        Credential bytes were excluded at capture. Direction, timestamp, byte
        count, and integrity digest remain retained.
      </div>
    );
  }

  if (detail === null) {
    return (
      <div className={cx("story-wire-load")}>
        <button disabled={loading} type="button" onClick={load}>
          <FileJson2 size={15} />
          {loading ? "Loading exact bytes…" : "Open exact socket content"}
        </button>
        {error ? <p role="alert">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className={cx("story-wire-body")}>
      <pre>{detail.content_text}</pre>
      <details>
        <summary>Integrity and byte representation</summary>
        <div className={cx("story-detail-body")}>
          <dl className={cx("story-provenance")}>
            <div><dt>Direction</dt><dd>{detail.direction}</dd></div>
            <div><dt>Bytes</dt><dd>{detail.bytes.toLocaleString()}</dd></div>
            <div><dt>Digest</dt><dd className={cx("mono")}>{detail.digest}</dd></div>
          </dl>
          <pre>{detail.content_base64}</pre>
        </div>
      </details>
    </div>
  );
}
