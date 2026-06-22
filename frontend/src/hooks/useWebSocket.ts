import { useEffect, useRef, useState } from "react";

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
  const [connected, setConnected] = useState<boolean>(false);

  // Keep the latest handler in a ref so a changed callback identity doesn't
  // tear down and reopen the socket.
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | undefined;
    let reconnectDelay = reconnectInterval;
    let disposed = false;

    function connect() {
      ws = new WebSocket(url);

      ws.onopen = () => {
        setConnected(true);
        reconnectDelay = reconnectInterval;
      };

      ws.onmessage = (event) => {
        try {
          onMessageRef.current(JSON.parse(event.data));
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (disposed) return;
        // Exponential backoff reconnect
        reconnectTimeout = setTimeout(() => {
          reconnectDelay = Math.min(reconnectDelay * 2, maxReconnectInterval);
          connect();
        }, reconnectDelay);
      };

      ws.onerror = () => {
        ws?.close();
      };
    }

    connect();

    return () => {
      disposed = true;
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (ws) {
        ws.onclose = null; // Prevent reconnect on intentional close
        ws.close();
      }
      setConnected(false);
    };
  }, [url, reconnectInterval, maxReconnectInterval]);

  return { connected };
}
