#!/usr/bin/env python3
"""
Flask monitoring dashboard using ThreadSafeRegistry.

Demonstrates thread-safe registry access from Flask request handlers.

Usage:
    pip install flask
    python 01_flask_monitoring.py

Then visit:
    http://localhost:5000/api/operations - List all operations
    http://localhost:5000/api/statistics - Get statistics
    http://localhost:5000/ - Simple HTML dashboard
"""

import threading
import time

import anyio
from flask import Flask, jsonify, render_template_string

from hother.cancelable import AnyioBridge, Cancelable, OperationStatus, ThreadSafeRegistry

app = Flask(__name__)


# HTML Template for dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Cancelable Operations Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .stats { background: #f0f0f0; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .operations { margin-top: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        .status-running { color: blue; }
        .status-completed { color: green; }
        .status-cancelled { color: orange; }
        .status-failed { color: red; }
        button { padding: 5px 10px; cursor: pointer; }
    </style>
    <script>
        function refreshData() {
            // Refresh statistics
            fetch('/api/statistics')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('stats').innerHTML = `
                        <h2>Statistics</h2>
                        <p>Active Operations: ${data.active_operations}</p>
                        <p>History Size: ${data.history_size}</p>
                        <p>Average Duration: ${data.average_duration_seconds.toFixed(2)}s</p>
                    `;
                });

            // Refresh operations list
            fetch('/api/operations')
                .then(response => response.json())
                .then(data => {
                    const tbody = document.getElementById('operations-body');
                    tbody.innerHTML = data.map(op => `
                        <tr>
                            <td>${op.id.substring(0, 8)}...</td>
                            <td>${op.name || 'unnamed'}</td>
                            <td class="status-${op.status}">${op.status}</td>
                            <td>${op.duration ? op.duration.toFixed(2) + 's' : 'N/A'}</td>
                            <td>
                                ${op.status === 'running' || op.status === 'pending'
                                    ? `<button onclick="cancelOperation('${op.id}')">Cancel</button>`
                                    : ''}
                            </td>
                        </tr>
                    `).join('');
                });
        }

        function cancelOperation(opId) {
            fetch(`/api/operations/${opId}/cancel`, { method: 'POST' })
                .then(() => {
                    alert('Cancelation scheduled');
                    setTimeout(refreshData, 500);
                });
        }

        // Auto-refresh every 2 seconds
        setInterval(refreshData, 2000);
        // Initial load
        window.onload = refreshData;
    </script>
</head>
<body>
    <h1>Cancelable Operations Dashboard</h1>

    <div id="stats" class="stats">
        <h2>Statistics</h2>
        <p>Loading...</p>
    </div>

    <div class="operations">
        <h2>Active Operations</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="operations-body">
                <tr><td colspan="5">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    """Serve the dashboard HTML."""
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/operations")
def list_operations():
    """
    List all active operations.

    This endpoint is called from Flask request handlers (threads),
    so we use ThreadSafeRegistry for safe access.
    """
    registry = ThreadSafeRegistry()
    operations = registry.list_operations()

    return jsonify(
        [
            {
                "id": op.id,
                "name": op.name,
                "status": op.status.value,
                "duration": op.duration_seconds,
                "parent_id": op.parent_id,
            }
            for op in operations
        ]
    )


@app.route("/api/operations/<status>")
def list_operations_by_status(status):
    """List operations filtered by status."""
    try:
        status_enum = OperationStatus(status.upper())
    except ValueError:
        return jsonify({"error": f"Invalid status: {status}"}), 400

    registry = ThreadSafeRegistry()
    operations = registry.list_operations(status=status_enum)

    return jsonify(
        [
            {
                "id": op.id,
                "name": op.name,
                "status": op.status.value,
                "duration": op.duration_seconds,
            }
            for op in operations
        ]
    )


@app.route("/api/statistics")
def get_statistics():
    """
    Get operation statistics.

    Thread-safe access from Flask request handler.
    """
    registry = ThreadSafeRegistry()
    stats = registry.get_statistics()
    return jsonify(stats)


@app.route("/api/operations/<op_id>/cancel", methods=["POST"])
def cancel_operation(op_id):
    """
    Cancel a specific operation.

    Note: This schedules the cancelation asynchronously via AnyioBridge
    and returns immediately. The actual cancelation happens in the
    async event loop.
    """
    registry = ThreadSafeRegistry()
    registry.cancel_operation(op_id, message="Cancelled via API")

    return jsonify({"status": "scheduled", "message": "Cancelation scheduled"}), 202


@app.route("/api/operations/cancel-all", methods=["POST"])
def cancel_all_operations():
    """Cancel all operations."""
    registry = ThreadSafeRegistry()
    registry.cancel_all(message="Bulk cancel via API")

    return jsonify({"status": "scheduled", "message": "Bulk cancelation scheduled"}), 202


@app.route("/api/history")
def get_history():
    """Get operation history."""
    limit = int(request.args.get("limit", 100))

    registry = ThreadSafeRegistry()
    history = registry.get_history(limit=limit)

    return jsonify(
        [
            {
                "id": op.id,
                "name": op.name,
                "status": op.status.value,
                "duration": op.duration_seconds,
                "completed_at": op.end_time.isoformat() if op.end_time else None,
            }
            for op in history
        ]
    )


# Background task simulator
async def simulate_operations():
    """
    Simulate some long-running operations for demo purposes.

    In a real application, these would be your actual async operations.
    """
    import random

    while True:
        # Create a new operation
        async with Cancelable(name=f"Task-{random.randint(1000, 9999)}") as cancel:
            try:
                # Simulate work
                duration = random.uniform(5, 15)
                print(f"Starting operation {cancel.context.id} for {duration:.1f}s")

                await cancel.report_progress("Starting work...")
                await anyio.sleep(duration / 2)

                await cancel.report_progress("50% complete...")
                await anyio.sleep(duration / 2)

                await cancel.report_progress("Completed")
                print(f"Operation {cancel.context.id} completed")
            except anyio.get_cancelled_exc_class():
                print(f"⚠️  Operation {cancel.context.id} was cancelled")
                raise

        # Wait before starting next operation
        await anyio.sleep(random.uniform(2, 5))


async def run_async_app():
    """Run the async application (operations + bridge)."""
    bridge = AnyioBridge.get_instance()

    async with anyio.create_task_group() as tg:
        # Start the anyio bridge for thread-safe cancelation
        tg.start_soon(bridge.start)

        # Start operation simulator
        tg.start_soon(simulate_operations)

        # Keep running
        print("Async application started")
        print("Visit http://localhost:5000/ for the dashboard")

        # Run forever (until interrupted)
        await anyio.sleep_forever()


def run_flask():
    """Run Flask in a separate thread."""
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


def main():
    """
    Main entry point.

    Starts both:
    - Flask web server (in a thread)
    - Async operations and AnyioBridge (in main thread)
    """
    print("Starting Flask monitoring dashboard example")

    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Give Flask time to start
    time.sleep(1)

    print("Flask started on http://localhost:5000/")
    print("Press Ctrl+C to stop")

    # Run async application in main thread
    try:
        anyio.run(run_async_app)
    except KeyboardInterrupt:
        print("Shutting down...")


if __name__ == "__main__":
    main()
