import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, deleteDocument, listDocuments, uploadDocument, type DocumentInfo } from "../api";
import { isAdmin, useAuth } from "../session";

const POLL_MS = 2000;
const ACCEPT = ".pdf,.md,.markdown,.txt";

export default function DocumentsPage() {
  const { user } = useAuth();
  const canUpload = isAdmin(user);
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const [confirming, setConfirming] = useState<number | null>(null); // id awaiting "really delete?"
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Bumping this number reloads the list (after an upload, a retry, or a poll tick).
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let cancelled = false;
    listDocuments()
      .then((all) => {
        if (cancelled) return;
        setDocs(all);
        setLoadError(null);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : "Could not load documents.");
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

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

  async function onDelete(doc: DocumentInfo) {
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteDocument(doc.id);
      setConfirming(null);
      refresh();
    } catch (err) {
      setDeleteError(`${doc.filename}: ${err instanceof ApiError ? err.message : "could not delete."}`);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section className="page">
      <h1>Documents</h1>
      {canUpload ? (
        <p className="muted">
          Upload PDF, Markdown or text files. Uploading a file with the same name replaces the old version.
        </p>
      ) : (
        <p className="muted">
          The company documents the assistant answers from. Only admins can add, replace or delete documents.
        </p>
      )}

      {canUpload && (
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
      )}

      {deleteError && (
        <div className="notice error" role="alert">
          {deleteError}
        </div>
      )}

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

      {docs?.length === 0 && (
        <p className="notice">
          {canUpload ? "No documents yet. Upload one to get started." : "No documents yet. An admin needs to add some."}
        </p>
      )}

      {docs && docs.length > 0 && (
        <table className="docs">
          <thead>
            <tr>
              <th>File</th>
              <th>Type</th>
              <th>Status</th>
              <th className="num">Chunks</th>
              {canUpload && <th aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>
                  <div className="doc-title">{d.title}</div>
                  <div className="muted small">{d.filename}</div>
                </td>
                <td>{d.file_type.toUpperCase()}</td>
                <td>
                  <span className={`badge ${d.status}`}>{d.status}</span>
                  {d.error && <div className="row-error">{d.error}</div>}
                </td>
                <td className="num">{d.chunk_count}</td>
                {canUpload && (
                  <td className="doc-actions">
                    {confirming === d.id ? (
                      <span className="confirm">
                        Delete it? Answers stop using it at once.{" "}
                        <button className="link danger" onClick={() => onDelete(d)} disabled={deleting}>
                          {deleting ? "Deleting…" : "Delete"}
                        </button>{" "}
                        <button className="link" onClick={() => setConfirming(null)} disabled={deleting}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button className="link danger" onClick={() => setConfirming(d.id)} aria-label={`Delete ${d.filename}`}>
                        Delete
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
