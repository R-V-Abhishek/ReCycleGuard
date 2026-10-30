import { useEffect, useRef, useState } from "react";
import type { EvidenceRef, Locator } from "../api/types";
import { useClient } from "../state/session";
import { ErrorBanner, Mono, Unavailable, useLoad } from "./common";

export function describeLocator(locator: Locator | null | undefined): string {
  if (!locator) return "no locator";
  switch (locator.kind) {
    case "PDF_PAGE":
      return `PDF page ${locator.page_index_1based}`;
    case "PDF_CELL":
      return `PDF page ${locator.page_index_1based}, table ${locator.table_id}, cell ${locator.cell_row}:${locator.cell_column}`;
    case "CSV_ROW":
      return `CSV row ${locator.row_index_1based}${locator.column_name ? `, ${locator.column_name}` : ""}`;
    case "JSON_POINTER":
      return `JSON ${locator.json_pointer}`;
    case "TEXT_SPAN":
      return `Text ${locator.text_start}-${locator.text_end}`;
    case "DB_RECORD":
      return "Database record";
  }
}

function PdfView({ blob, startPage }: { blob: Blob; startPage: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [page, setPage] = useState(startPage);
  const [pages, setPages] = useState<number | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    let cancelled = false;
    let cancelRender: (() => void) | undefined;
    let closeDocument: (() => void) | undefined;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        const data = new Uint8Array(await blob.arrayBuffer());
        const loading = pdfjs.getDocument({ data });
        closeDocument = () => void loading.destroy();
        const document = await loading.promise;
        if (cancelled) return;
        setPages(document.numPages);
        const pdfPage = await document.getPage(Math.min(Math.max(page, 1), document.numPages));
        const viewport = pdfPage.getViewport({ scale: 1.4 });
        const target = canvas.current;
        if (!target || cancelled) return;
        target.width = viewport.width;
        target.height = viewport.height;
        const task = pdfPage.render({ canvas: target, viewport });
        cancelRender = () => task.cancel();
        await task.promise;
      } catch (cause) {
        if (!cancelled) setError(cause);
      }
    })();
    return () => {
      cancelled = true;
      cancelRender?.();
      closeDocument?.();
    };
  }, [blob, page]);
  return (
    <div>
      <ErrorBanner error={error} />
      <div className="row">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {pages ?? "…"}
        </span>
        <button disabled={pages !== null && page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
      <canvas ref={canvas} className="pdf" />
    </div>
  );
}

function TextView({ text, locator }: { text: string; locator: Locator | null | undefined }) {
  if (locator?.kind === "TEXT_SPAN" && locator.text_start !== null && locator.text_end !== null) {
    return (
      <pre className="block">
        {text.slice(0, locator.text_start)}
        <mark>{text.slice(locator.text_start, locator.text_end)}</mark>
        {text.slice(locator.text_end)}
      </pre>
    );
  }
  if (locator?.kind === "CSV_ROW" && locator.row_index_1based !== null) {
    // Line 0 is the header, so data row N is line N.
    return (
      <pre className="block">
        {text.split(/\r?\n/).map((line, index) =>
          index === locator.row_index_1based ? (
            <mark key={index}>{line + "\n"}</mark>
          ) : (
            <span key={index}>{line + "\n"}</span>
          ),
        )}
      </pre>
    );
  }
  return <pre className="block">{text}</pre>;
}

const isText = (type: string) =>
  type.startsWith("text/") || type.includes("json") || type.includes("csv");

function DownloadOnly({ blob, name }: { blob: Blob; name: string }) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    const created = URL.createObjectURL(blob);
    setUrl(created);
    return () => URL.revokeObjectURL(created);
  }, [blob]);
  return (
    <p>
      This file type isn't displayed in the browser.{" "}
      {url && (
        <a href={url} download={name}>
          Download {name}
        </a>
      )}
    </p>
  );
}

function ArtifactBody({ blob, name, locator }: { blob: Blob; name: string; locator?: Locator | null }) {
  const [text, setText] = useState<string>();
  const type = blob.type.toLowerCase();
  useEffect(() => {
    if (isText(type)) void blob.text().then(setText);
  }, [blob, type]);
  if (type.includes("pdf")) return <PdfView blob={blob} startPage={locator?.page_index_1based ?? 1} />;
  if (isText(type)) return text === undefined ? <p>Loading…</p> : <TextView text={text} locator={locator} />;
  return <DownloadOnly blob={blob} name={name} />;
}

export function ArtifactViewer({
  dossierId,
  revisionId,
  name,
  locator,
  onClose,
}: {
  dossierId: string;
  revisionId: string;
  name?: string | null;
  locator?: Locator | null;
  onClose(): void;
}) {
  const client = useClient();
  const { data, error, loading } = useLoad(
    () => client.artifact(dossierId, revisionId),
    [client, dossierId, revisionId],
  );
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <header className="card-head">
          <div>
            <h2>{name ?? "Original evidence"}</h2>
            <div className="muted small">
              <Mono>{revisionId}</Mono> · {describeLocator(locator)}
            </div>
          </div>
          <button onClick={onClose}>Close</button>
        </header>
        <ErrorBanner error={error} />
        {loading && <p>Loading…</p>}
        {data && <ArtifactBody blob={data} name={name ?? "artifact"} locator={locator} />}
      </div>
    </div>
  );
}

// Evidence links. Only references the API returned can be opened, and only through the
// dossier-scoped artifact route. Provision and record references without an artifact stay inert.
export function EvidenceChips({
  refs,
  dossierId,
  onCalculation,
}: {
  refs: EvidenceRef[];
  dossierId?: string;
  onCalculation?(id: string): void;
}) {
  const client = useClient();
  const [open, setOpen] = useState<{ revisionId: string; locator: Locator | null } | null>(null);
  const [error, setError] = useState<unknown>();
  if (!refs.length) return <Unavailable label="none recorded" />;
  const activate = async (ref: EvidenceRef) => {
    setError(undefined);
    if (ref.ref_kind === "CALCULATION") return onCalculation?.(ref.ref_id);
    if (ref.artifact_revision_id) {
      return setOpen({ revisionId: ref.artifact_revision_id, locator: ref.locator });
    }
    if (ref.ref_kind === "OBSERVATION" && dossierId) {
      try {
        const evidence = await client.evidence(dossierId);
        const found = evidence.observations.find((o) => o.observation_id === ref.ref_id);
        if (found) setOpen({ revisionId: found.artifact_revision_id, locator: found.locator });
        else setError(new Error(`${ref.ref_id} is not in this dossier's current evidence.`));
      } catch (cause) {
        setError(cause);
      }
    }
  };
  const openable = (ref: EvidenceRef) =>
    ref.ref_kind === "CALCULATION"
      ? Boolean(onCalculation)
      : Boolean(dossierId && (ref.artifact_revision_id || ref.ref_kind === "OBSERVATION"));
  return (
    <div className="chips">
      {refs.map((ref, index) =>
        openable(ref) ? (
          <button key={index} className="chip" title={describeLocator(ref.locator)} onClick={() => void activate(ref)}>
            {ref.ref_kind} <Mono>{ref.ref_id}</Mono>
          </button>
        ) : (
          <span key={index} className="chip inert" title={describeLocator(ref.locator)}>
            {ref.ref_kind} <Mono>{ref.ref_id}</Mono>
          </span>
        ),
      )}
      <ErrorBanner error={error} />
      {open && dossierId && (
        <ArtifactViewer
          dossierId={dossierId}
          revisionId={open.revisionId}
          locator={open.locator}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}
