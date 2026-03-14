import { deleteDocument } from "../api";
import "./Sidebar.css";

export default function Sidebar({ documents, onDocumentDeleted }) {
  const handleDelete = async (docId) => {
    if (!confirm("Delete this document and all its embeddings?")) return;
    try {
      await deleteDocument(docId);
      onDocumentDeleted(docId);
    } catch (err) {
      alert("Failed to delete: " + err.message);
    }
  };

  return (
    <div className="sidebar">
      <h3>Uploaded Documents</h3>
      {documents.length === 0 ? (
        <p className="no-docs">No documents yet.</p>
      ) : (
        <ul className="doc-list">
          {documents.map((doc) => (
            <li key={doc.document_id} className="doc-item">
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
      <div className="sidebar-footer">
        <p>
          Free tier: ~200 MB of documents. Supports PDF, DOCX, TXT, CSV.
        </p>
      </div>
    </div>
  );
}
