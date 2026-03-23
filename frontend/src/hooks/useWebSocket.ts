import { useEffect, useRef, useCallback, useState } from "react";

interface UseWebSocketOptions {
  url: string;
  onMessage: (data: unknown) => void;
  reconnectInterval?: number;
  maxReconnectInterval?: number;
}

export function useWebSocket({
  url,
  onMessage,
  reconnectInterval = 1000,
  maxReconnectInterval = 30000,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectDelayRef = useRef<number>(reconnectInterval);
  const [connected, setConnected] = useState<boolean>(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      reconnectDelayRef.current = reconnectInterval;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Exponential backoff reconnect
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectDelayRef.current = Math.min(
          reconnectDelayRef.current * 2,
          maxReconnectInterval,
        );
        connect();
      }, reconnectDelayRef.current);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [url, onMessage, reconnectInterval, maxReconnectInterval]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
    };
  }, [connect]);

  return { connected };
}
