import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, listDocuments, uploadDocument, type DocumentInfo } from "../api";

const POLL_MS = 2000;
const ACCEPT = ".pdf,.md,.markdown,.txt";

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setDocs(await listDocuments());
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not load documents.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll only while something is still processing, so status updates without a reload.
  const anyProcessing = docs?.some((d) => d.status === "processing") ?? false;
  useEffect(() => {
    if (!anyProcessing) return;
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [anyProcessing, refresh]);

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setUploadErrors([]);
    const errors: string[] = [];
    for (const file of Array.from(files)) {
      try {
        await uploadDocument(file);
      } catch (err) {
        errors.push(`${file.name}: ${err instanceof ApiError ? err.message : "upload failed."}`);
      }
    }
    setUploadErrors(errors);
    setUploading(false);
    if (fileInput.current) fileInput.current.value = "";
    refresh();
  }

  return (
    <section className="page">
      <h1>Documents</h1>
      <p className="muted">
        Upload PDF, Markdown or text files. Uploading a file with the same name replaces the old version.
      </p>

      <label className={`upload ${uploading ? "disabled" : ""}`}>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          multiple
          disabled={uploading}
          onChange={(e) => onUpload(e.target.files)}
        />
        {uploading ? "Uploading…" : "Choose files to upload"}
      </label>

      {uploadErrors.length > 0 && (
        <div className="notice error" role="alert">
          {uploadErrors.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </div>
      )}

      {loadError && (
        <div className="notice error" role="alert">
          {loadError} <button onClick={refresh}>Retry</button>
        </div>
      )}

      {docs === null && !loadError && <p className="muted">Loading documents…</p>}

      {docs?.length === 0 && <p className="notice">No documents yet. Upload one to get started.</p>}

      {docs && docs.length > 0 && (
        <table className="docs">
          <thead>
            <tr>
              <th>File</th>
              <th>Type</th>
              <th>Status</th>
              <th className="num">Chunks</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td>{d.file_type.toUpperCase()}</td>
                <td>
                  <span className={`badge ${d.status}`}>{d.status}</span>
                  {d.error && <div className="row-error">{d.error}</div>}
                </td>
                <td className="num">{d.chunk_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
