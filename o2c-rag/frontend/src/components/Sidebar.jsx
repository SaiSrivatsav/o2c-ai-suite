import { useRef, useState, useCallback } from "react";
import { deleteDocument, uploadDocument } from "../api";
import "./Sidebar.css";

const ACCEPTED = ".pdf,.docx,.txt,.csv";

export default function Sidebar({ documents, onDocumentDeleted, onUploadComplete }) {
  const fileRef = useRef();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const handleDelete = async (docId) => {
    if (!confirm("Delete this document and all its embeddings?")) return;
    try {
      await deleteDocument(docId);
      onDocumentDeleted(docId);
    } catch (err) {
      alert("Failed to delete: " + err.message);
    }
  };

  const handleFile = useCallback(
    async (file) => {
      if (!file) return;
      setError(null);
      setUploading(true);
      try {
        const doc = await uploadDocument(file);
        onUploadComplete(doc);
      } catch (err) {
        setError(err.message);
      } finally {
        setUploading(false);
        if (fileRef.current) fileRef.current.value = "";
      }
    },
    [onUploadComplete]
  );

  return (
    <div className="sidebar">
      <div className="sidebar-section">
        <div className="section-header">
          <h3>Documents</h3>
          <button
            className="btn-upload-sm"
            onClick={() => !uploading && fileRef.current?.click()}
            disabled={uploading}
            title="Upload document"
          >
            {uploading ? (
              <span className="spinner-sm" />
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED}
            hidden
            onChange={(e) => handleFile(e.target.files[0])}
          />
        </div>

        {error && <div className="upload-error-sm">{error}</div>}

        {documents.length === 0 ? (
          <p className="no-docs">No documents uploaded yet.</p>
        ) : (
          <ul className="doc-list">
            {documents.map((doc) => (
              <li key={doc.document_id} className="doc-item">
                <div className="doc-icon">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                  </svg>
                </div>
                <div className="doc-info">
                  <span className="doc-name" title={doc.filename}>
                    {doc.filename}
                  </span>
                  <span className="doc-meta">
                    {doc.chunks} chunks &middot; {doc.file_size_mb} MB
                  </span>
                </div>
                <button
                  className="btn-delete"
                  onClick={() => handleDelete(doc.document_id)}
                  title="Delete document"
                >
                  &times;
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="sidebar-footer">
        <p>PDF, DOCX, TXT, CSV &middot; Max 200 MB</p>
      </div>
    </div>
  );
}
