"""Progress for background uploads running in this API process."""

from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

_jobs = {}
_lock = Lock()


def has_processing_jobs():
    with _lock:
        return any(job["status"] == "PROCESSING" for job in _jobs.values())


def create_job(kind, filename, update_target=None):
    with _lock:
        if len(_jobs) >= 1000:
            for old_id, old_job in list(_jobs.items()):
                if old_job["status"] != "PROCESSING":
                    del _jobs[old_id]
                if len(_jobs) < 500:
                    break
        if update_target and any(
            job["status"] == "PROCESSING" and job.get("update_target") == update_target
            for job in _jobs.values()
        ):
            raise HTTPException(status_code=409, detail="That upload is already being replaced.")
        job_id = uuid4().hex
        _jobs[job_id] = {
            "job_id": job_id, "kind": kind, "filename": filename,
            "update_target": update_target, "status": "PROCESSING",
            "processed": 0, "rows_total": 0, "rows_imported": 0, "rows_skipped": 0,
            "error_message": None,
        }
        return job_id


def update_job(job_id, **values):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(values)


def get_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Upload job not found. Check upload history for its final status.")
        return {key: value for key, value in job.items() if key != "update_target"}
