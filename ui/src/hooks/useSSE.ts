import { useEffect, useRef, useState } from "react";

/**
 * Универсальный SSE-hook. Держит последние `limit` событий.
 * Автоматически переподключается при разрыве.
 */
export function useSSE<T = any>(url: string, limit = 100): {
  events: T[];
  connected: boolean;
  lastEventAt: number | null;
} {
  const [events, setEvents] = useState<T[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const bufRef = useRef<T[]>([]);

  useEffect(() => {
    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      es = new EventSource(url);
      es.onopen = () => setConnected(true);
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          bufRef.current = [data, ...bufRef.current].slice(0, limit);
          setEvents([...bufRef.current]);
          setLastEventAt(Date.now());
        } catch (e) {
          console.warn("SSE parse", e);
        }
      };
      es.onerror = () => {
        setConnected(false);
        es?.close();
        reconnectTimer = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      es?.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, [url, limit]);

  return { events, connected, lastEventAt };
}
