import axios from "axios";

// use env variable
const BASE_URL = import.meta.env.VITE_API_URL;

const API = axios.create({
  baseURL: `${BASE_URL}/api`,
  timeout: 60000,
});

export const scraperAPI = {
  startScrape: (data) => API.post("/scrape", data),
  getStatus: (jobId) => API.get(`/scrape/${jobId}`),
  getPreview: (jobId) => API.get(`/scrape/${jobId}/preview`),

  // dynamic download URL
  download: (jobId) => `${BASE_URL}/api/download/${jobId}`,
};