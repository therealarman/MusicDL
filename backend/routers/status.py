import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..services.queue import jobs

router = APIRouter()


@router.get("/status/{job_id}")
async def status_stream(job_id: str, request: Request) -> EventSourceResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    async def event_generator():
        # Replay all buffered events first
        for event in list(job.events):
            if await request.is_disconnected():
                return
            yield {
                "event": event["event_type"],
                "data": json.dumps(event["data"]),
            }

        # If job already finished, we're done
        if job.status.value in ("done", "cancelled", "error"):
            return

        # Stream new events as they arrive
        while True:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(job.event_queue.get(), timeout=25.0)
                yield {
                    "event": event["event_type"],
                    "data": json.dumps(event["data"]),
                }
                if event["event_type"] == "done":
                    return
            except asyncio.TimeoutError:
                # Keepalive ping
                yield {"event": "heartbeat", "data": "{}"}

    return EventSourceResponse(event_generator())
