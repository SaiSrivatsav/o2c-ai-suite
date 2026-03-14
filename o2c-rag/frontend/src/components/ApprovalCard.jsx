import { useState } from "react";
import "./ApprovalCard.css";

export default function ApprovalCard({ data, onRespond, disabled }) {
  const [comment, setComment] = useState("");
  const [responded, setResponded] = useState(false);

  const handle = (approved) => {
    setResponded(true);
    onRespond(approved, comment);
  };

  if (responded) {
    return null;
  }

  return (
    <div className="approval-card">
      <div className="approval-header">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span>Approval Required</span>
      </div>

      {data.reason && <p className="approval-reason">{data.reason}</p>}

      {data.details && (
        <div className="approval-details">
          {Object.entries(data.details).map(([k, v]) => (
            <div key={k} className="detail-row">
              <span className="detail-key">{k.replace(/_/g, " ")}:</span>
              <span className="detail-val">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
            </div>
          ))}
        </div>
      )}

      <textarea
        className="approval-comment"
        placeholder="Optional comment…"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        rows={2}
        disabled={disabled}
      />

      <div className="approval-actions">
        <button
          className="btn-reject"
          onClick={() => handle(false)}
          disabled={disabled}
        >
          Reject
        </button>
        <button
          className="btn-approve"
          onClick={() => handle(true)}
          disabled={disabled}
        >
          Approve
        </button>
      </div>
    </div>
  );
}
