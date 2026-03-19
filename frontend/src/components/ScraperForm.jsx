import { useState } from "react";
import { scraperAPI } from "../services/api";

export default function ScraperForm({
  setJobId,
  setStatus,
  setPreview,
  isSearching,
  setIsSearching,
}) {
  const [form, setForm] = useState({
    source: "justdial",
    keyword: "",
    city: "",
    max_results: 20,
    max_time: 240,
  });

  const handleSubmit = async () => {
    const keyword = form.keyword.trim();
    const city = form.city.trim();
    const maxResults = Math.min(Math.max(Number(form.max_results) || 1, 1), 20);

    if (!keyword || !city) {
      alert("Enter keyword and city");
      return;
    }

    if (isSearching) {
      return;
    }

    setIsSearching(true);
    setStatus(null);
    setPreview([]);
    setJobId(null);

    try {
      const payload = {
        ...form,
        keyword,
        city,
        max_results: maxResults,
      };

      const res = await scraperAPI.startScrape(payload);
      setJobId(res.data.job_id);
    } catch (err) {
      setIsSearching(false);
      setStatus({
        status: "failed",
        message: "Failed to start scraper",
      });
      alert("Failed to start scraper");
    }
  };

  return (
    <div className="scraper-form-card">
      <div className="section-intro">
        <h2>Run Scraper</h2>
        <p>
          Configure your scraping source, target keyword, and location to start
          a new lead collection job.
        </p>
      </div>

      <div className="form-grid">
        <div className="form-group form-group-full">
          <label>Data Source</label>
          <select
            value={form.source}
            disabled={isSearching}
            onChange={(e) => setForm({ ...form, source: e.target.value })}
            className="ui-input"
          >
            <option value="justdial">Justdial</option>
            <option value="google_maps">Google Maps</option>
          </select>
        </div>

        <div className="form-group">
          <label>Keyword</label>
          <input
            placeholder="e.g. electrical contractor"
            value={form.keyword}
            disabled={isSearching}
            onChange={(e) => setForm({ ...form, keyword: e.target.value })}
            className="ui-input"
          />
        </div>

        <div className="form-group">
          <label>City</label>
          <input
            placeholder="e.g. Delhi"
            value={form.city}
            disabled={isSearching}
            onChange={(e) => setForm({ ...form, city: e.target.value })}
            className="ui-input"
          />
        </div>

        <div className="form-group">
          <label>Max Results</label>
          <input
            type="number"
            placeholder="Max Results"
            min="1"
            max="20"
            value={form.max_results}
            disabled={isSearching}
            onChange={(e) => {
              const value = Number(e.target.value);
              const safeValue = Math.min(Math.max(value || 1, 1), 20);
              setForm({ ...form, max_results: safeValue });
            }}
            className="ui-input"
          />
        </div>

        <div className="form-group">
          <div className="info-box">
            <div className="info-box-label">Job Mode</div>
            <div className="info-box-value">Async scraping with live polling status</div>
          </div>
        </div>
      </div>

      <div className="form-footer">
        <p className="helper-text">
          Current limit: up to 20 final requested results per job.
        </p>

        <button onClick={handleSubmit} disabled={isSearching} className="primary-btn">
          {isSearching ? "Searching..." : "Run Search"}
        </button>
      </div>
    </div>
  );
}