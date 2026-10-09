import { useEffect, useRef, useState } from "react";
import { getUploadJobProgress } from "../api";

export default function useUploadJob(storageKey, onFinished, onPollError) {
  const [jobId, setJobId] = useState(() => sessionStorage.getItem(storageKey) || "");
  const [progress, setProgress] = useState(null);
  const finishedRef = useRef(onFinished);
  const errorRef = useRef(onPollError);
  finishedRef.current = onFinished;
  errorRef.current = onPollError;

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer;
    async function poll() {
      try {
        const job = await getUploadJobProgress(jobId);
        if (cancelled) return;
        setProgress(job);
        if (job.status === "COMPLETED" || job.status === "FAILED") {
          sessionStorage.removeItem(storageKey);
          setJobId("");
          finishedRef.current?.(job);
        } else {
          timer = setTimeout(poll, 1500);
        }
      } catch (error) {
        if (cancelled) return;
        errorRef.current?.(error);
        if (error.status === 404) {
          sessionStorage.removeItem(storageKey);
          setJobId("");
        } else {
          timer = setTimeout(poll, 5000);
        }
      }
    }
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [jobId, storageKey]);

  function begin(job) {
    sessionStorage.setItem(storageKey, job.job_id);
    setProgress({ ...job, processed: 0, rows_total: 0, rows_imported: 0, rows_skipped: 0 });
    setJobId(job.job_id);
  }

  return { begin, jobId, progress };
}
