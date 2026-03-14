import { useState, useRef, useCallback } from "react";
import { uploadDocument } from "../api";
import "./FileUpload.css";

const ACCEPTED = ".pdf,.docx,.txt,.csv";

export default function FileUpload({ onUploadComplete }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef();

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

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div className="upload-section">
      <div
        className={`drop-zone ${dragging ? "dragging" : ""} ${uploading ? "busy" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && fileRef.current?.click()}
      >
        {uploading ? (
          <div className="upload-status">
            <div className="spinner" />
            <p>Processing document...</p>
            <p className="hint">Chunking, embedding & storing in Pinecone</p>
          </div>
        ) : (
          <>
            <div className="upload-icon">📄</div>
            <p className="upload-title">Drop a file here or click to upload</p>
            <p className="hint">Supports PDF, DOCX, TXT, CSV — Max 200 MB</p>
          </>
        )}
      </div>

      <input
        ref={fileRef}
        type="file"
        accept={ACCEPTED}
        hidden
        onChange={(e) => handleFile(e.target.files[0])}
      />

      {error && <div className="upload-error">{error}</div>}
    </div>
  );
}
