import { useEffect, useRef, useState } from "react";
import type { CanonicalEvent } from "./types";

/** Subscribe to GET /runs/{id}/events via EventSource.
 *  Backfill + live events arrive on the same stream; the server dedupes. */
export function useEventStream(runId: string | null) {
  const [events, setEvents] = useState<CanonicalEvent[]>([]);
  const [streamEnded, setStreamEnded] = useState(false);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    setEvents([]);
    setStreamEnded(false);
    seen.current = new Set();
    if (!runId) return;

    const es = new EventSource(`/runs/${runId}/events`);

    es.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as CanonicalEvent;
        if (event.event_id && seen.current.has(event.event_id)) return;
        if (event.event_id) seen.current.add(event.event_id);
        setEvents((prev) => [...prev, event]);
      } catch { /* ignore malformed frames */ }
    };

    es.addEventListener("end", () => {
      setStreamEnded(true);
      es.close();
    });

    es.onerror = () => {
      // EventSource auto-reconnects; backfill dedup makes that safe.
    };

    return () => es.close();
  }, [runId]);

  return { events, streamEnded };
}
