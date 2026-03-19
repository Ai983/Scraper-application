import axios from "axios";

const API = axios.create({
  baseURL: "http://localhost:8000/api",
  timeout: 60000,
});

export const scraperAPI = {
  startScrape: (data) => API.post("/scrape", data),
  getStatus: (jobId) => API.get(`/scrape/${jobId}`),
  getPreview: (jobId) => API.get(`/scrape/${jobId}/preview`),
  download: (jobId) => `http://localhost:8000/api/download/${jobId}`,
};