#!/bin/bash
# Clears stored meetings/action items + Streamlit cache, starts the app, opens it in the browser.
set -e

PROJECT_DIR="/Users/saisreed/Desktop/meetingpilot"
PORT=8501
LOG_FILE="$PROJECT_DIR/scripts/streamlit.log"

cd "$PROJECT_DIR"

# Stop any previous instance of this app.
pkill -f "streamlit run app.py" 2>/dev/null || true
sleep 1

# Clear the meetings DB (meetings + action_items tables).
"$PROJECT_DIR/.venv/bin/python" -c "from meetingpilot.memory import clear_all_data; clear_all_data()"

# Clear Streamlit's function cache.
"$PROJECT_DIR/.venv/bin/streamlit" cache clear

# Start the server in the background, headless (no auto browser tab from Streamlit itself).
nohup "$PROJECT_DIR/.venv/bin/streamlit" run app.py --server.headless true \
  > "$LOG_FILE" 2>&1 &

# Wait for the server to come up, then open the browser.
for i in $(seq 1 30); do
  if curl -s "http://localhost:$PORT" > /dev/null; then
    open "http://localhost:$PORT"
    echo "MeetingPilot is running at http://localhost:$PORT"
    read -n 1 -s -r -p "Press any key to close this window..."
    exit 0
  fi
  sleep 1
done

echo "Streamlit did not come up in time. Check $LOG_FILE"
read -n 1 -s -r -p "Press any key to close this window..."
exit 1
