// Custom hooks for bot API and WebSocket

import { useState, useEffect, useCallback, useRef } from 'react';
import { BotStatus, PositionSet, BotConfig, EquityHistoryResponse, WSMessage } from '../types';

const API_BASE = '/api';
const WS_URL = window.location.protocol === 'https:' ? 'wss://' + window.location.host + '/ws' : 'ws://' + window.location.host + '/ws';

export function useWebSocket() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [positions, setPositions] = useState<PositionSet[]>([]);
  const [connected, setConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const shouldReconnect = useRef(true);
  const intentionalClose = useRef(false);

  const connect = useCallback(() => {
    try {
      intentionalClose.current = false;
      const socket = new WebSocket(WS_URL);
      ws.current = socket;

      socket.onopen = () => {
        console.log('WebSocket connected');
        setConnected(true);

        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
        }

        heartbeatInterval.current = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 20000);
      };

      socket.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data);

          if (message.type === 'status' || message.type === 'status_update') {
            setStatus(message.data);
          } else if (message.type === 'positions' || message.type === 'positions_update') {
            setPositions(message.data);
          }
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      socket.onerror = (error) => {
        if (intentionalClose.current) {
          return;
        }
        console.error('WebSocket error:', error);
      };

      socket.onclose = () => {
        if (ws.current === socket) {
          ws.current = null;
        }
        setConnected(false);

        if (heartbeatInterval.current) {
          clearInterval(heartbeatInterval.current);
          heartbeatInterval.current = null;
        }

        if (intentionalClose.current || !shouldReconnect.current) {
          return;
        }

        console.log('WebSocket disconnected');
        reconnectTimeout.current = setTimeout(() => {
          console.log('Reconnecting...');
          connect();
        }, 3000);
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
    }
  }, []);

  useEffect(() => {
    shouldReconnect.current = true;
    connect();

    return () => {
      shouldReconnect.current = false;
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
        reconnectTimeout.current = null;
      }
      if (heartbeatInterval.current) {
        clearInterval(heartbeatInterval.current);
        heartbeatInterval.current = null;
      }
      if (ws.current) {
        intentionalClose.current = true;
        ws.current.onopen = null;
        ws.current.onmessage = null;
        ws.current.onerror = null;
        ws.current.onclose = null;
        ws.current.close();
        ws.current = null;
      }
    };
  }, [connect]);

  return { status, positions, connected };
}

export function useAPI() {
  const startBot = async () => {
    const response = await fetch(`${API_BASE}/start`, { method: 'POST' });
    return response.json();
  };

  const stopBot = async () => {
    const response = await fetch(`${API_BASE}/stop`, { method: 'POST' });
    return response.json();
  };

  const emergencyStop = async () => {
    const response = await fetch(`${API_BASE}/emergency-stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify('Emergency stop by user'),
    });
    return response.json();
  };

  const closePosition = async (setId: string) => {
    const response = await fetch(`${API_BASE}/positions/${setId}/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify('Manual close'),
    });
    return response.json();
  };

  const closeAllPositions = async () => {
    const response = await fetch(`${API_BASE}/positions/close-all`, { method: 'POST' });
    return response.json();
  };

  const removePosition = async (setId: string, force: boolean = false) => {
    const query = force ? '?force=true' : '';
    const response = await fetch(`${API_BASE}/positions/${setId}${query}`, { method: 'DELETE' });
    return response.json();
  };

  const getConfig = async (): Promise<BotConfig> => {
    const response = await fetch(`${API_BASE}/config`);
    return response.json();
  };

  const updateConfig = async (config: BotConfig) => {
    const response = await fetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config }),
    });
    return response.json();
  };

  const getEquityHistory = async (limit: number = 240): Promise<EquityHistoryResponse> => {
    const response = await fetch(`${API_BASE}/equity/history?limit=${limit}`);
    return response.json();
  };

  return {
    startBot,
    stopBot,
    emergencyStop,
    closePosition,
    closeAllPositions,
    removePosition,
    getConfig,
    updateConfig,
    getEquityHistory,
  };
}
