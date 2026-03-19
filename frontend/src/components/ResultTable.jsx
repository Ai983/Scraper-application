import { scraperAPI } from "../services/api";

export default function ResultTable({ preview, status, jobId }) {
  if (!status) return null;

  return (
    <div className="results-card">
      <div className="results-top">
        <div>
          <h2>Results</h2>
          <p>Current job status and scraped lead preview.</p>
        </div>

        <span className="results-status-pill">Status: {status.status}</span>
      </div>

      {status.status === "completed" && (
        <div className="results-content">
          <div className="results-actions">
            <div>
              <p className="results-title">Scrape completed successfully</p>
              <p className="results-subtitle">
                Review the preview below or export the full result as CSV.
              </p>
            </div>

            <a
              href={scraperAPI.download(jobId)}
              target="_blank"
              rel="noreferrer"
              className="primary-btn"
            >
              Download CSV
            </a>
          </div>

          <div className="table-wrap">
            <table className="results-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>City</th>
                  <th>Rating</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((row, i) => (
                  <tr key={i}>
                    <td>{row.business_name}</td>
                    <td>{row.phone}</td>
                    <td>{row.city}</td>
                    <td>{row.rating}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {preview.length === 0 && (
              <div className="empty-state">No preview rows available.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}