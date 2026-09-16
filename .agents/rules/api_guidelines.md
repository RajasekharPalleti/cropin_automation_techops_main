---
description: Guidelines for Server-Sent Events (SSE) and API communication.
---
# API & Server-Sent Events (SSE) Guidelines

This project uses FastAPI with `StreamingResponse` to push real-time updates to the frontend via Server-Sent Events (SSE). Whenever you create a new automation task or long-running script, you MUST follow these guidelines:

1. **Backend Routing (FastAPI)**
   - Use `asyncio.Queue` to manage state between the execution thread and the streaming response.
   - Define a callback `async def on_update(msg): await queue.put({"status": "progress", "message": msg})` and pass it to the automation function.
   - The stream generator should `yield f"data: {json.dumps(event)}\n\n"`.
   - Ensure you break the loop when `status` is `"success"` or `"error"`.

2. **Frontend Handling (JavaScript)**
   - The frontend consumes SSE via `fetch` or `EventSource`.
   - When calling these endpoints, ensure you correctly parse the `data: ` chunks and handle the stream until it closes.
   - Example implementation can be found in `static/js/update_phone.js` or `static/js/execution.js`.

3. **Exception Handling**
   - Always wrap the main executor in a `try...except` block.
   - Upon exception, push `{"status": "error", "message": str(e)}` to the queue so the frontend knows the task failed gracefully rather than hanging indefinitely.
