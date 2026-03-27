# Seat Allocation Algorithm Comparator

Pure Python 3 / tkinter tool to compare seat allocation strategies while avoiding previous seatmates.

## Requirements
- Python 3.x
- No third-party libraries required

## Running
```bash
python main.py
```

## Features
- Three algorithms: Las Vegas, Conflict-Driven Swapping, Backtracking
- Light-themed tkinter UI with controls, seating grid (6 columns), and metrics
- Reads prior pairs from `history.json` and only writes when **Save to File** is clicked
- Detailed debug logging to `app.log`

## Usage
1. Enter a student count that is a multiple of 6.
2. Choose an algorithm and click **Start Allocation** to view the seating.
3. Click **Save to File** to append the seating pairs to `history.json`.
4. Use **Reset** to clear the grid and metrics.
