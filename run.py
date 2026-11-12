#!/usr/bin/env python3
"""Group 3 — Protocol Visualizer. One command to start everything."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
