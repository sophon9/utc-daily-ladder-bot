"""WebSocket endpoint for real-time updates."""
import logging
import asyncio
import json
from typing import Set
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept new connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_message(self, websocket: WebSocket, message: dict) -> bool:
        """Send message to specific connection."""
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.disconnect(websocket)
            return False

    async def broadcast(self, message: dict):
        """Broadcast message to all connections."""
        if not self.active_connections:
            return

        # Create tasks for all sends
        tasks = []
        for connection in list(self.active_connections):
            tasks.append(self._safe_send(connection, message))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, websocket: WebSocket, message: dict):
        """Safely send message, handling disconnections."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.debug(f"Connection lost during send: {e}")
            self.disconnect(websocket)


# Global connection manager
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, bot):
    """
    WebSocket endpoint for real-time updates.

    Sends periodic updates about bot status, positions, and PnL.
    """
    await manager.connect(websocket)

    try:
        # Send initial status
        status = bot.get_status()
        equity = await bot.get_equity()
        if equity is not None:
            status["equity"] = equity

        if not await manager.send_message(websocket, {
            "type": "status",
            "timestamp": datetime.now().isoformat(),
            "data": status,
        }):
            return

        positions = bot.position_manager.get_all_sets()
        if not await manager.send_message(websocket, {
            "type": "positions",
            "timestamp": datetime.now().isoformat(),
            "data": [ps.to_dict() for ps in positions],
        }):
            return

        # Listen for messages and send periodic updates
        update_task = asyncio.create_task(send_periodic_updates(websocket, bot))

        try:
            while True:
                # Receive messages from client (if any)
                data = await websocket.receive_text()
                message = json.loads(data)

                # Handle client requests
                if message.get("type") == "ping":
                    if not await manager.send_message(websocket, {
                        "type": "pong",
                        "timestamp": datetime.now().isoformat(),
                    }):
                        break

                elif message.get("type") == "request_status":
                    status = bot.get_status()
                    equity = await bot.get_equity()
                    if equity is not None:
                        status["equity"] = equity

                    if not await manager.send_message(websocket, {
                        "type": "status",
                        "timestamp": datetime.now().isoformat(),
                        "data": status,
                    }):
                        break

                elif message.get("type") == "request_positions":
                    positions = bot.position_manager.get_all_sets()
                    if not await manager.send_message(websocket, {
                        "type": "positions",
                        "timestamp": datetime.now().isoformat(),
                        "data": [ps.to_dict() for ps in positions],
                    }):
                        break

        except WebSocketDisconnect:
            pass
        finally:
            update_task.cancel()

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)


async def send_periodic_updates(websocket: WebSocket, bot):
    """Send periodic updates to client."""
    while True:
        try:
            # Wait before sending update
            await asyncio.sleep(5)

            # Send status update
            status = bot.get_status()
            equity = await bot.get_equity()
            if equity is not None:
                status["equity"] = equity

            if not await manager.send_message(websocket, {
                "type": "status_update",
                "timestamp": datetime.now().isoformat(),
                "data": status,
            }):
                break

            # Send positions update
            positions = bot.position_manager.get_all_sets()
            if not await manager.send_message(websocket, {
                "type": "positions_update",
                "timestamp": datetime.now().isoformat(),
                "data": [ps.to_dict() for ps in positions],
            }):
                break

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error sending periodic update: {e}")
            await asyncio.sleep(5)


async def broadcast_event(event_type: str, data: dict):
    """Broadcast event to all connected clients."""
    await manager.broadcast({
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        "data": data,
    })
