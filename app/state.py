"""
app/state.py
------------
Shared application state: the ConnectionManager class and the module-level
singleton instances used by both main.py (lifespan) and routes.py (endpoints).
"""

import asyncio
from datetime import datetime
from typing import Dict, List

from app.core.backup_manager import BackupManager
from app.script_configs import SSE_HEARTBEAT_TIMEOUT


# ---------------------------------------------------------------------------
# Custom exception – raised inside a running script thread to signal cancellation
# ---------------------------------------------------------------------------

class JobStoppedException(BaseException):
    """Inherits from BaseException (not Exception) so it bypasses broad
    `except Exception` blocks inside script modules."""
    pass


# ---------------------------------------------------------------------------
# Connection / session manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        # Map client_id -> asyncio.Queue (for live streaming)
        self.active_connections: Dict[str, asyncio.Queue] = {}
        # Map client_id -> List[Tuple[int, str]] (for history/replay: (id, message))
        self.client_logs: Dict[str, List[tuple]] = {}
        # Map client_id -> int (current sequence number)
        self.client_counters: Dict[str, int] = {}

        # ACTIVE MACHINE LOCKS (One script per machine per user)
        # Key format: "{tenant}:{username}:{machine_id}"
        self.active_machines: set = set()
        # Map client_id -> machine_lock_key for cleanup
        self.client_machine_map: Dict[str, str] = {}

        # Set of client_ids with active running tasks
        self.active_tasks: set = set()
        # Map client_id -> script_name (for recovery)
        self.client_script_map: Dict[str, str] = {}
        # Set of client_ids that requested cancellation
        self.cancellation_requests: set = set()

    # ------------------------------------------------------------------
    # Lock / unlock helpers
    # ------------------------------------------------------------------

    def mark_active(self, client_id: str, machine_key: str, script_name: str = None):
        self.active_tasks.add(client_id)
        if script_name:
            self.client_script_map[client_id] = script_name
        if machine_key:
            self.client_machine_map[client_id] = machine_key
            self.active_machines.add(machine_key)

        # Ensure no pending cancel request from a previous run
        if client_id in self.cancellation_requests:
            self.cancellation_requests.remove(client_id)

    def mark_inactive(self, client_id: str):
        if client_id in self.active_tasks:
            self.active_tasks.remove(client_id)

        # Cleanup script name
        self.client_script_map.pop(client_id, None)

        # Cleanup machine lock
        machine_key = self.client_machine_map.pop(client_id, None)
        if machine_key and machine_key in self.active_machines:
            self.active_machines.remove(machine_key)

        if client_id in self.cancellation_requests:
            self.cancellation_requests.remove(client_id)

    def request_cancel(self, client_id: str):
        self.cancellation_requests.add(client_id)

    def detach_job(self, client_id: str):
        """
        Immediately removes the job from active status and drops its machine locks,
        but KEEPS it in the cancellation_requests set.
        This forces the UI to unlock even if the backend script is stuck in a loop
        or slow network call. The background thread will still encounter the cancellation
        flag on its next log_callback and terminate.
        """
        self.cancellation_requests.add(client_id)

        if client_id in self.active_tasks:
            self.active_tasks.remove(client_id)

        self.client_script_map.pop(client_id, None)

        machine_key = self.client_machine_map.pop(client_id, None)
        if machine_key and machine_key in self.active_machines:
            self.active_machines.remove(machine_key)

    def is_cancelled(self, client_id: str) -> bool:
        return client_id in self.cancellation_requests

    def is_active(self, client_id: str) -> bool:
        return client_id in self.active_tasks

    def is_machine_active(self, machine_key: str) -> bool:
        return machine_key in self.active_machines

    # ------------------------------------------------------------------
    # SSE connection helpers
    # ------------------------------------------------------------------

    async def connect(self, client_id: str, last_event_id: str = None):
        """Register (or re-register) a client's SSE queue and replay history."""
        if client_id in self.active_connections:
            print(f"DEBUG: Client {client_id} reconnecting. Replacing old connection queue.")

        self.active_connections[client_id] = asyncio.Queue()
        print(f"Client {client_id} connected for SSE. Last-Event-ID: {last_event_id}")

        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        if client_id in self.client_logs and self.client_logs[client_id]:
            if last_event_id:
                await self.active_connections[client_id].put((0, f"{timestamp} Connected to server (SSE) - Resuming session..."))
            else:
                await self.active_connections[client_id].put((0, f"{timestamp} Connected to server (SSE)."))

            for (msg_id, message) in self.client_logs[client_id]:
                if not last_event_id or (last_event_id.isdigit() and msg_id > int(last_event_id)):
                    await self.active_connections[client_id].put((msg_id, message))
        else:
            self.client_logs[client_id] = []
            self.client_counters[client_id] = 0
            await self.active_connections[client_id].put((0, f"{timestamp} Connected to server (SSE)."))

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            print(f"Client {client_id} disconnected.")

    async def send_log(self, message: str, client_id: str):
        """Archive a log message and push it to the live SSE queue.

        SSE uses newline characters as frame delimiters, so any \n embedded
        inside a message would silently truncate it in the browser.  We split
        on newlines and send each non-empty line as its own SSE event.  Empty
        lines (e.g. a leading \n used for visual spacing) are sent as a blank
        log entry so the UI still renders a gap row.
        """
        is_control = any(message.startswith(p) for p in ["JOB_COMPLETED::", "JOB_FAILED::", "JOB_STOPPED::"])

        if client_id not in self.client_logs:
            self.client_logs[client_id] = []
            self.client_counters[client_id] = 0

        # Control/sentinel messages are never multi-line – send as-is.
        if is_control or message == "STOP_UI_NOW":
            self.client_counters[client_id] += 1
            msg_id = self.client_counters[client_id]
            self.client_logs[client_id].append((msg_id, message))
            if client_id in self.active_connections:
                await self.active_connections[client_id].put((msg_id, message))
            return

        # Split on newlines so embedded \n never breaks the SSE frame.
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        lines = message.split("\n")
        for line in lines:
            # Blank lines become an empty timestamped entry (visual spacer).
            formatted = f"{timestamp} {line}" if line.strip() else ""
            self.client_counters[client_id] += 1
            msg_id = self.client_counters[client_id]
            self.client_logs[client_id].append((msg_id, formatted))
            if client_id in self.active_connections:
                await self.active_connections[client_id].put((msg_id, formatted))

    async def stream_logs(self, client_id: str):
        """Generator that yields SSE-formatted messages for a client."""
        try:
            if client_id not in self.active_connections:
                return

            # Capture this queue so we can detect if a new connection replaced it
            current_queue = self.active_connections[client_id]

            while True:
                # Exit if a newer connection has replaced this one
                if self.active_connections.get(client_id) is not current_queue:
                    print(f"Closing stale connection for {client_id} (Replaced by new connection).")
                    break

                try:
                    data = await asyncio.wait_for(current_queue.get(), timeout=SSE_HEARTBEAT_TIMEOUT)

                    if isinstance(data, tuple):
                        msg_id, message = data
                        if msg_id > 0:
                            yield f"id: {msg_id}\ndata: {message}\n\n"
                        else:
                            yield f"data: {message}\n\n"
                    else:
                        yield f"data: {data}\n\n"

                except asyncio.TimeoutError:
                    # Heartbeat keeps the TCP connection alive when idle
                    yield ": keepalive\n\n"

        except asyncio.CancelledError:
            if self.active_connections.get(client_id) is current_queue:
                self.disconnect(client_id)
            print(f"Stream cancelled for {client_id}")

    def clear_logs(self, client_id: str):
        if client_id in self.client_logs:
            self.client_logs[client_id] = []
            self.client_counters[client_id] = 0


# ---------------------------------------------------------------------------
# Module-level singletons — import these everywhere instead of re-creating
# ---------------------------------------------------------------------------

manager = ConnectionManager()
backup_manager = BackupManager()
