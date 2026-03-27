import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import messagebox


LOG_FILE = "app.log"
HISTORY_FILE = "history.json"
LIGHT_BG = "#f8f9fa"
HIGHLIGHT_BG = "#d4edda"
PAIR_BORDER = "#dee2e6"
BUTTON_PRIMARY = "#0d6efd"
BUTTON_SECONDARY = "#6c757d"
BUTTON_RESET = "#dc3545"


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


def arrangement_to_pairs(arrangement: List[str]) -> List[Tuple[str, str]]:
    return [
        (arrangement[i], arrangement[i + 1])
        for i in range(0, len(arrangement), 2)
    ]


class HistoryManager:
    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, List[List[List[str]]]] = {"sessions": []}
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.path.exists():
            logger.debug("History file missing, creating new one at %s", self.path)
            self._write()
        else:
            self._read()

    def _read(self) -> None:
        try:
            with self.path.open("r", encoding="utf-8") as f:
                self.data = json.load(f)
            if "sessions" not in self.data or not isinstance(self.data["sessions"], list):
                logger.warning("Invalid history structure, resetting.")
                self.data = {"sessions": []}
                self._write()
            logger.debug("Loaded history with %d sessions", len(self.data["sessions"]))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read history: %s. Resetting file.", exc)
            self.data = {"sessions": []}
            self._write()

    def _write(self) -> None:
        try:
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            logger.debug("History written to %s", self.path)
        except OSError as exc:
            logger.error("Failed to write history: %s", exc)
            raise

    def get_previous_pairs(self) -> Set[frozenset]:
        pairs: Set[frozenset] = set()
        for session in self.data.get("sessions", []):
            for pair in session:
                if len(pair) == 2:
                    pairs.add(frozenset(pair))
        logger.debug("Computed %d historical pairs", len(pairs))
        return pairs

    def append_session(self, pairs: List[Tuple[str, str]]) -> None:
        logger.debug("Appending session with %d pairs", len(pairs))
        self.data.setdefault("sessions", []).append([list(p) for p in pairs])
        self._write()


class AllocationError(Exception):
    pass


class BaseAllocator:
    name: str = ""
    complexity: str = ""

    def allocate(self, students: List[str], previous_pairs: Set[frozenset]) -> List[str]:
        raise NotImplementedError

    @staticmethod
    def has_conflict(arrangement: List[str], previous_pairs: Set[frozenset]) -> bool:
        for a, b in arrangement_to_pairs(arrangement):
            if frozenset((a, b)) in previous_pairs:
                return True
        return False


class LasVegasAllocator(BaseAllocator):
    name = "Las Vegas"
    complexity = "Expected O(k·N)"

    def __init__(self, max_retries: int = 2000):
        self.max_retries = max_retries

    def allocate(self, students: List[str], previous_pairs: Set[frozenset]) -> List[str]:
        logger.debug("Starting Las Vegas allocation with max %d retries", self.max_retries)
        attempts = 0
        students_copy = students[:]
        while attempts < self.max_retries:
            random.shuffle(students_copy)
            attempts += 1
            if not self.has_conflict(students_copy, previous_pairs):
                logger.debug("Las Vegas succeeded after %d attempts", attempts)
                return students_copy[:]
        logger.error("Las Vegas failed after %d attempts", attempts)
        raise AllocationError("Las Vegas algorithm could not find a valid seating within retry limit.")


class ConflictSwappingAllocator(BaseAllocator):
    name = "Conflict-Driven Swapping"
    complexity = "O(N²)"

    def __init__(self, max_iterations: int = 3000):
        self.max_iterations = max_iterations

    def _find_conflicts(self, arrangement: List[str], previous_pairs: Set[frozenset]) -> List[int]:
        conflicts = []
        for idx, (a, b) in enumerate(arrangement_to_pairs(arrangement)):
            if frozenset((a, b)) in previous_pairs:
                conflicts.append(idx * 2)
        return conflicts

    def allocate(self, students: List[str], previous_pairs: Set[frozenset]) -> List[str]:
        logger.debug("Starting Conflict-Driven Swapping allocation")
        arrangement = students[:]
        random.shuffle(arrangement)

        for iteration in range(self.max_iterations):
            conflicts = self._find_conflicts(arrangement, previous_pairs)
            if not conflicts:
                logger.debug("Conflict-Driven Swapping succeeded after %d iterations", iteration)
                return arrangement

            improved = False
            for conflict_idx in conflicts:
                for swap_idx in range(len(arrangement)):
                    if swap_idx in (conflict_idx, conflict_idx + 1):
                        continue
                    arrangement[conflict_idx], arrangement[swap_idx] = (
                        arrangement[swap_idx],
                        arrangement[conflict_idx],
                    )
                    new_conflicts = self._find_conflicts(arrangement, previous_pairs)
                    if len(new_conflicts) < len(conflicts):
                        logger.debug(
                            "Swapped indices %d and %d reduced conflicts from %d to %d",
                            conflict_idx,
                            swap_idx,
                            len(conflicts),
                            len(new_conflicts),
                        )
                        improved = True
                        break
                    arrangement[conflict_idx], arrangement[swap_idx] = (
                        arrangement[swap_idx],
                        arrangement[conflict_idx],
                    )
                if improved:
                    break
            if not improved:
                logger.debug("No improvement found in iteration %d", iteration)
        logger.error("Conflict-Driven Swapping failed after %d iterations", self.max_iterations)
        raise AllocationError("Conflict-Driven Swapping could not resolve conflicts in time.")


class BacktrackingAllocator(BaseAllocator):
    name = "Backtracking"
    complexity = "O(N!)"

    def allocate(self, students: List[str], previous_pairs: Set[frozenset]) -> List[str]:
        logger.debug("Starting Backtracking allocation")
        arrangement: List[str] = []
        used: Set[str] = set()

        def is_valid(pos: int) -> bool:
            if pos % 2 == 1:
                a, b = arrangement[pos - 1], arrangement[pos]
                if frozenset((a, b)) in previous_pairs:
                    return False
            return True

        def dfs() -> bool:
            if len(arrangement) == len(students):
                return True
            for student in students:
                if student in used:
                    continue
                arrangement.append(student)
                used.add(student)
                if is_valid(len(arrangement) - 1):
                    if dfs():
                        return True
                used.remove(student)
                arrangement.pop()
            return False

        if dfs():
            logger.debug("Backtracking succeeded")
            return arrangement[:]
        logger.error("Backtracking failed to find valid arrangement")
        raise AllocationError("Backtracking could not find a valid seating arrangement.")


ALLOCATORS: Dict[str, BaseAllocator] = {
    "las_vegas": LasVegasAllocator(),
    "conflict_swapping": ConflictSwappingAllocator(),
    "backtracking": BacktrackingAllocator(),
}


@dataclass
class AllocationResult:
    arrangement: List[str]
    execution_ms: float
    complexity: str
    algorithm_name: str


class SeatAllocationApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Seat Allocation Algorithm Comparator")
        self.root.configure(bg=LIGHT_BG)
        self.root.geometry("1000x700")
        self.root.minsize(900, 600)

        self.history_manager = HistoryManager(Path(HISTORY_FILE))
        self.previous_pairs = self.history_manager.get_previous_pairs()

        self.selected_algorithm = tk.StringVar(value="las_vegas")
        self.student_count_var = tk.StringVar(value="12")

        self.current_result: Optional[AllocationResult] = None
        self.seat_labels: List[tk.Label] = []

        self._build_layout()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=3)
        self.root.rowconfigure(1, weight=1)

        control_frame = tk.Frame(self.root, bg=LIGHT_BG, padx=12, pady=12, bd=1, relief="solid")
        control_frame.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(12, 6), pady=12)

        seating_frame = tk.Frame(self.root, bg=LIGHT_BG, padx=12, pady=12, bd=1, relief="solid")
        seating_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=(12, 6))

        metrics_frame = tk.Frame(self.root, bg=LIGHT_BG, padx=12, pady=12, bd=1, relief="solid")
        metrics_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(6, 12))

        # Controls
        tk.Label(control_frame, text="Seat Allocation", bg=LIGHT_BG, font=("Helvetica", 16, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 16)
        )

        tk.Label(control_frame, text="Number of Students (multiple of 6):", bg=LIGHT_BG, anchor="w").grid(
            row=1, column=0, sticky="w"
        )
        tk.Entry(control_frame, textvariable=self.student_count_var, width=20).grid(
            row=2, column=0, sticky="we", pady=(4, 12)
        )

        tk.Label(control_frame, text="Algorithm:", bg=LIGHT_BG, anchor="w").grid(row=3, column=0, sticky="w")
        algo_frame = tk.Frame(control_frame, bg=LIGHT_BG)
        algo_frame.grid(row=4, column=0, sticky="we", pady=(4, 12))

        tk.Radiobutton(
            algo_frame,
            text="Las Vegas",
            variable=self.selected_algorithm,
            value="las_vegas",
            bg=LIGHT_BG,
            anchor="w",
        ).pack(fill="x", pady=1)
        tk.Radiobutton(
            algo_frame,
            text="Conflict-Driven Swapping",
            variable=self.selected_algorithm,
            value="conflict_swapping",
            bg=LIGHT_BG,
            anchor="w",
        ).pack(fill="x", pady=1)
        tk.Radiobutton(
            algo_frame,
            text="Backtracking",
            variable=self.selected_algorithm,
            value="backtracking",
            bg=LIGHT_BG,
            anchor="w",
        ).pack(fill="x", pady=1)

        tk.Button(
            control_frame,
            text="Start Allocation",
            command=self.start_allocation,
            bg=BUTTON_PRIMARY,
            fg="white",
            relief="flat",
            padx=10,
            pady=6,
        ).grid(row=5, column=0, sticky="we", pady=(4, 6))

        tk.Button(
            control_frame,
            text="Save to File",
            command=self.save_allocation,
            bg=BUTTON_SECONDARY,
            fg="white",
            relief="flat",
            padx=10,
            pady=6,
        ).grid(row=6, column=0, sticky="we", pady=6)

        tk.Button(
            control_frame,
            text="Reset",
            command=self.reset,
            bg=BUTTON_RESET,
            fg="white",
            relief="flat",
            padx=10,
            pady=6,
        ).grid(row=7, column=0, sticky="we", pady=6)

        # Seating grid
        tk.Label(seating_frame, text="Seating Chart (6 columns, paired seats)", bg=LIGHT_BG, font=("Helvetica", 14, "bold")).pack(
            anchor="w", pady=(0, 12)
        )
        self.grid_container = tk.Frame(seating_frame, bg=LIGHT_BG)
        self.grid_container.pack(fill="both", expand=True)

        # Metrics
        tk.Label(metrics_frame, text="Metrics", bg=LIGHT_BG, font=("Helvetica", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.complexity_var = tk.StringVar(value="Time Complexity: -")
        self.exec_time_var = tk.StringVar(value="Execution Time: - ms")

        tk.Label(metrics_frame, textvariable=self.complexity_var, bg=LIGHT_BG, anchor="w", font=("Helvetica", 12)).grid(
            row=1, column=0, sticky="w", pady=(8, 4)
        )
        tk.Label(metrics_frame, textvariable=self.exec_time_var, bg=LIGHT_BG, anchor="w", font=("Helvetica", 12)).grid(
            row=2, column=0, sticky="w", pady=4
        )

        for i in range(2):
            metrics_frame.rowconfigure(i, weight=1)
        metrics_frame.columnconfigure(0, weight=1)

    def _validate_student_count(self) -> int:
        try:
            count = int(self.student_count_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid integer for the number of students.")
            logger.error("Student count is not an integer")
            raise
        if count <= 0 or count % 6 != 0:
            messagebox.showerror("Invalid Input", "Number of students must be a positive multiple of 6.")
            logger.error("Student count %d is not a positive multiple of 6", count)
            raise ValueError("Invalid student count")
        return count

    def start_allocation(self) -> None:
        logger.debug("Start Allocation button clicked")
        try:
            student_count = self._validate_student_count()
        except Exception:
            return

        students = [f"Student {i+1}" for i in range(student_count)]
        algo_key = self.selected_algorithm.get()
        allocator = ALLOCATORS.get(algo_key)
        if allocator is None:
            messagebox.showerror("Algorithm Error", "Selected algorithm is not available.")
            logger.error("Allocator for key %s not found", algo_key)
            return

        logger.debug("Selected algorithm: %s", allocator.name)
        start_time = time.perf_counter()
        try:
            arrangement = allocator.allocate(students, self.previous_pairs)
        except Exception as exc:
            logger.exception("Allocation failed: %s", exc)
            messagebox.showerror("Allocation Error", str(exc))
            return
        end_time = time.perf_counter()

        execution_ms = (end_time - start_time) * 1000
        self.current_result = AllocationResult(
            arrangement=arrangement,
            execution_ms=execution_ms,
            complexity=allocator.complexity,
            algorithm_name=allocator.name,
        )
        logger.debug(
            "Allocation successful using %s in %.2f ms", allocator.name, execution_ms
        )
        self._render_grid(arrangement)
        self._update_metrics()

    def save_allocation(self) -> None:
        logger.debug("Save to File button clicked")
        if not self.current_result:
            messagebox.showerror("No Allocation", "Please run an allocation before saving.")
            return
        pairs = arrangement_to_pairs(self.current_result.arrangement)
        try:
            self.history_manager.append_session(pairs)
            self.previous_pairs = self.history_manager.get_previous_pairs()
            messagebox.showinfo("Saved", "Allocation saved to history.json.")
            logger.debug("Allocation saved; total sessions now %d", len(self.history_manager.data.get("sessions", [])))
        except Exception as exc:
            logger.exception("Failed to save allocation: %s", exc)
            messagebox.showerror("Save Error", "Failed to save allocation.")

    def reset(self) -> None:
        logger.debug("Reset button clicked")
        self.current_result = None
        self.complexity_var.set("Time Complexity: -")
        self.exec_time_var.set("Execution Time: - ms")
        for label in self.seat_labels:
            label.destroy()
        self.seat_labels = []

    def _render_grid(self, arrangement: List[str]) -> None:
        logger.debug("Rendering grid for %d students", len(arrangement))
        for label in self.seat_labels:
            label.destroy()
        self.seat_labels = []

        rows = (len(arrangement) + 5) // 6
        for r in range(rows):
            for c in range(6):
                idx = r * 6 + c
                text = arrangement[idx] if idx < len(arrangement) else ""
                bg_color = HIGHLIGHT_BG if text else LIGHT_BG
                label = tk.Label(
                    self.grid_container,
                    text=text,
                    bg=bg_color,
                    width=14,
                    height=2,
                    relief="groove",
                    borderwidth=1,
                )
                padx = 4
                if c in (1, 3):
                    padx = (4, 16)
                elif c in (2, 4):
                    padx = (16, 4)
                label.grid(row=r, column=c, padx=padx, pady=4, sticky="nsew")
                self.seat_labels.append(label)

        for c in range(6):
            self.grid_container.columnconfigure(c, weight=1)
        for r in range(rows):
            self.grid_container.rowconfigure(r, weight=1)

    def _update_metrics(self) -> None:
        if not self.current_result:
            return
        self.complexity_var.set(f"Time Complexity: {self.current_result.complexity} ({self.current_result.algorithm_name})")
        self.exec_time_var.set(f"Execution Time: {self.current_result.execution_ms:.2f} ms")


def main() -> None:
    logger.info("Launching Seat Allocation Algorithm Comparator")
    root = tk.Tk()
    SeatAllocationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
