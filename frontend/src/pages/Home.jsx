import { useState } from "react";
import ScraperForm from "../components/ScraperForm";
import JobStatus from "../components/JobStatus";
import ResultTable from "../components/ResultTable";


export default function Home() {
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState(null);
  const [preview, setPreview] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  return (
    <div className="home-page">
      <div className="home-shell">
        <section className="hero-card">
          <div className="hero-top">
            
            <h1 className="hero-title">Data Scraper</h1>
            <p className="hero-subtitle">
              Run structured scraping jobs, monitor progress in real time, and
              review extracted results from your lead generation pipeline.
            </p>
          </div>

          <div className="section-body">
            <ScraperForm
              setJobId={setJobId}
              setStatus={setStatus}
              setPreview={setPreview}
              isSearching={isSearching}
              setIsSearching={setIsSearching}
            />
          </div>
        </section>

        {jobId && (
          <div className="content-stack">
            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h2>Job Progress</h2>
                  <p>Track scraping status and background processing updates.</p>
                </div>
                <div className="job-id-pill">Job ID: {jobId}</div>
              </div>

              <div className="section-body">
                <JobStatus
                  jobId={jobId}
                  status={status}
                  setStatus={setStatus}
                  setPreview={setPreview}
                  setIsSearching={setIsSearching}
                />
              </div>
            </section>

            <section className="panel-card">
              <div className="panel-header">
                <div>
                  <h2>Results Preview</h2>
                  <p>Review scraped output and exported records.</p>
                </div>
              </div>

              <div className="section-body">
                <ResultTable preview={preview} status={status} jobId={jobId} />
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}