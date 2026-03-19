import { useEffect } from "react";
import { scraperAPI } from "../services/api";

const POLL_INTERVAL_MS = 3000;
const MAX_RUNNING_TIME_MS = 20 * 60 * 1000;
const MAX_CONSECUTIVE_ERRORS = 3;

export default function JobStatus({
  jobId,
  status,
  setStatus,
  setPreview,
  setIsSearching,
}) {
  useEffect(() => {
    if (!jobId) return;

    let intervalId = null;
    let isActive = true;
    const startedAt = Date.now();
    let consecutiveErrors = 0;

    const stopPolling = () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };

    const finishSearching = () => {
      if (isActive) {
        setIsSearching(false);
      }
    };

    const pollStatus = async () => {
      if (!isActive) return;

      const elapsed = Date.now() - startedAt;
      if (elapsed > MAX_RUNNING_TIME_MS) {
        stopPolling();
        setStatus({
          status: "timeout",
          message:
            "The scraper is taking too long. Backend may have stopped or become unresponsive.",
        });
        finishSearching();
        return;
      }

      try {
        const res = await scraperAPI.getStatus(jobId);
        const data = res.data || {};
        consecutiveErrors = 0;
        setStatus(data);

        if (data.status === "completed") {
          try {
            const previewRes = await scraperAPI.getPreview(jobId);
            setPreview(previewRes.data.rows || []);
          } catch (previewErr) {
            setStatus((prev) => ({
              ...(prev || {}),
              status: "completed",
              message: "Scrape completed, but preview could not be loaded.",
            }));
          }

          stopPolling();
          finishSearching();
          return;
        }

        if (data.status === "failed" || data.status === "error") {
          stopPolling();
          finishSearching();
          return;
        }
      } catch (err) {
        consecutiveErrors += 1;

        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          stopPolling();
          setStatus({
            status: "failed",
            message: "Unable to reach backend while checking job status.",
          });
          finishSearching();
        }
      }
    };

    pollStatus();
    intervalId = setInterval(pollStatus, POLL_INTERVAL_MS);

    return () => {
      isActive = false;
      stopPolling();
    };
  }, [jobId, setPreview, setStatus, setIsSearching]);

  const currentStatus = status?.status || "running";
  const message = status?.message || "";

  const processed = Number(status?.processed || 0);
  const total = Number(status?.total || 0);
  const backendPercent = Number(status?.progress_percent || 0);

  const computedPercent =
    total > 0 ? Math.min(100, Math.max(0, Math.round((processed / total) * 100))) : 0;

  const progressPercent = total > 0 ? Math.max(backendPercent, computedPercent) : 0;

  const statusLabelMap = {
    queued: "Job queued...",
    running: "Job is running...",
    completed: "Job completed successfully.",
    failed: "Job failed.",
    error: "Job failed due to an error.",
    timeout: "Job timed out.",
  };

  const statusLabel = statusLabelMap[currentStatus] || `Job status: ${currentStatus}`;

  return (
    <div className="job-status-card">
      <div className="status-top">
        <div>
          <h3>Job Status</h3>
          <p>Live backend polling and real-time processing updates.</p>
        </div>
        <span className={`status-badge status-${currentStatus}`}>{currentStatus}</span>
      </div>

      <div className="status-stack">
        <div className="status-box">
          <p className="status-label">{statusLabel}</p>
          {jobId ? <p className="status-subtext">Job ID: {jobId}</p> : null}
        </div>

        {currentStatus === "running" && total > 0 && (
          <div className="progress-card">
            <div className="progress-head">
              <div>
                <p className="progress-title">Processing Progress</p>
                <p className="progress-subtitle">
                  {processed} / {total} processed
                </p>
              </div>
              <div className="progress-percent">{progressPercent}%</div>
            </div>

            <div className="progress-track">
              <div
                className={`progress-fill progress-${currentStatus}`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        )}

        {currentStatus === "completed" && total > 0 && (
          <div className="success-box">
            Final progress: {total} / {total} processed (100%)
          </div>
        )}

        {message ? <div className="message-box">{message}</div> : null}
      </div>
    </div>
  );
}