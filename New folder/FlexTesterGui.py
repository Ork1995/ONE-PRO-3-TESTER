import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import time
import json
import re
import os
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

class LogAnalyzerEngine:
    """
    Embedded LogAnalyzer logic adapted for GUI integration.
    v1.6 Fixes:
      - FIX 1: WM search window now uses grace_delta instead of hardcoded 30s
      - FIX 2: When no WM reading found in window, shows nearest available reading for diagnostics
    """
    def __init__(self, log_content, config_path, printer_callback):
        self.log_content = log_content
        self.config_path = config_path
        self.printer = printer_callback
        self.events = []
        self.config = {}
        self.log_start_date = None
        self.log_weekday_index = None
        self.log_weekday_name = "Unknown"

    def log(self, msg):
        self.printer(msg)

    def load_config(self):
        try:
            if not os.path.exists(self.config_path):
                self.log(f"Config file not found: {self.config_path}")
                return False

            with open(self.config_path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)

            if isinstance(data, list):
                self.config = data
            elif isinstance(data, dict):
                self.config = [data]
            else:
                self.log("Invalid JSON format. Expected list or dict.")
                return False

            self.log(f"Loaded configuration with {len(self.config)} scenario(s) from {self.config_path}")
            return True
        except Exception as e:
            self.log(f"Error loading config: {e}")
            return False

    def parse_log(self):
        try:
            lines = self.log_content.splitlines()

            current_tracking_date = datetime.now()
            self.log_start_date = current_tracking_date

            header_pattern = re.compile(r'--- Log Started: (.+?) ---')
            date_change_pattern = re.compile(r'--- Date Changed: (.+?) ---')
            # Matches both old format: [HH:MM:SS] valve/wm N action
            # and new format:          [HH:MM:SS] valve/wm N action at HH:MM:SS | wm1=X wm2=X ...
            event_pattern    = re.compile(r'\[(\d{2}:\d{2}:\d{2})\] (valve|wm) (\d+) (.+)')
            nucleo_time_re   = re.compile(r' at (\d{2}:\d{2}:\d{2})')
            wm_snapshot_re   = re.compile(r'wm(\d+)=(\d+)')
            count_re         = re.compile(r'count (\d+)')

            self.events = []

            for line in lines:
                header_match = header_pattern.search(line)
                if header_match:
                    date_str = header_match.group(1)
                    try:
                        try:
                            new_date = datetime.strptime(date_str, "%c")
                        except ValueError:
                            new_date = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")

                        current_tracking_date = new_date

                        if len(self.events) == 0:
                            self.log_start_date = new_date
                            self.log_weekday_index = self.log_start_date.weekday()
                            self.log_weekday_name = self.log_start_date.strftime("%A")

                        self.log(f"Synced Date to: {current_tracking_date}")
                    except Exception as e:
                        self.log(f"Warning: Failed to parse header date: {e}")
                    continue

                dc_match = date_change_pattern.search(line)
                if dc_match:
                    date_str = dc_match.group(1)
                    try:
                        try:
                            new_date = datetime.strptime(date_str, "%c")
                        except ValueError:
                            new_date = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
                        current_tracking_date = new_date
                        self.log(f"Date updated mid-log to: {current_tracking_date}")
                    except:
                        pass
                    continue

                match = event_pattern.search(line)
                if match:
                    gui_timestamp, device_type, device_id, raw_action = match.groups()
                    raw_action = raw_action.strip()

                    # --- Always use PC (GUI) timestamp for analysis ---
                    # Nucleo 'at HH:MM:SS' is kept in log for info only
                    event_timestamp = gui_timestamp
                    nucleo_time_match = nucleo_time_re.search(raw_action)
                    if nucleo_time_match:
                        # Clean action: everything before " at HH:MM:SS"
                        action = raw_action[:nucleo_time_match.start()].strip().lower()
                    else:
                        action = raw_action.lower()
                        # Strip off '| wm1=...' snapshot if present
                        if '|' in action:
                            action = action[:action.index('|')].strip()

                    # --- Extract WM snapshot from "| wm1=X wm2=X ..." (new format) ---
                    wm_snapshot = {}
                    if '|' in raw_action:
                        snapshot_part = raw_action[raw_action.index('|') + 1:]
                        for sm in wm_snapshot_re.finditer(snapshot_part):
                            wm_snapshot[int(sm.group(1))] = int(sm.group(2))

                    # --- Extract pulse count from "count N" ---
                    count_val = 0
                    count_match = count_re.search(action)
                    if count_match:
                        count_val = int(count_match.group(1))

                    try:
                        t_part = datetime.strptime(event_timestamp, "%H:%M:%S").time()
                        full_dt = datetime.combine(current_tracking_date.date(), t_part)
                    except:
                        continue

                    self.events.append({
                        'time': str(full_dt),
                        'original_time': event_timestamp,
                        'full_time': full_dt,
                        'type': device_type,
                        'id': int(device_id),
                        'action': action,
                        'count': count_val,
                        'wm_snapshot': wm_snapshot
                    })

            if len(self.events) > 0:
                self.log(f"Parsed {len(self.events)} events spanning potentially multiple days.")
            else:
                self.log("No events found in log.")

        except Exception as e:
            self.log(f"Error parsing log: {e}")

    def _parse_time(self, time_str):
        try:
            if isinstance(time_str, str) and '-' in time_str and ':' in time_str:
                try:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    return dt
                except ValueError:
                    pass

            base_date = self.log_start_date if self.log_start_date else datetime.now()

            parsed_time = None
            if len(time_str.split(':')) == 2:
                parsed_time = datetime.strptime(time_str, "%H:%M")
            elif len(time_str.split(':')) == 3:
                parsed_time = datetime.strptime(time_str, "%H:%M:%S")

            if parsed_time:
                return datetime.combine(base_date.date(), parsed_time.time())

        except ValueError:
            return None
        return None

    def _parse_duration(self, duration_str):
        try:
            parts = duration_str.split(':')
            if len(parts) == 2:
                return timedelta(hours=int(parts[0]), minutes=int(parts[1]))
            elif len(parts) == 3:
                return timedelta(hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2]))
        except:
            return timedelta(0)
        return timedelta(0)

    def run_test(self):
        """
        Orchestrator: Iterates through all loaded scenarios. Supports Multi-Day Logs.
        """
        if not self.config:
            self.log("No configuration loaded.")
            return

        self.log("\n========================================")
        self.log(f"--- Starting Analysis of {len(self.config)} Scenarios ---")
        self.log("========================================")

        unique_dates = sorted(list(set(e['full_time'].date() for e in self.events if 'full_time' in e)))
        if not unique_dates:
            if self.log_start_date:
                unique_dates = [self.log_start_date.date()]
            else:
                unique_dates = [datetime.now().date()]

        self.log(f"Detected Activity on Dates: {[str(d) for d in unique_dates]}")

        final_verdict = True

        for current_date in unique_dates:
            self.log(f"\n#################################################")
            self.log(f"### Analyzing Day: {current_date.strftime('%A %Y-%m-%d')} ###")
            self.log(f"#################################################")

            day_verdict = True

            for index, scenario_config in enumerate(self.config):
                self.log(f"\n>>> Scenario #{index + 1}: {scenario_config.get('testname', 'Unnamed')} <<<")
                dummy_dt = datetime.combine(current_date, datetime.min.time())

                if not self._check_run_day(scenario_config, reference_date=dummy_dt):
                    if self._has_valve_activity_on_date(current_date):
                        self.log(f"  [FAIL] Irrigation detected on {current_date} but this day is NOT scheduled!")
                        day_verdict = False
                    else:
                        self.log(f"  [SKIP] No activity and not scheduled for {current_date}")
                    continue

                if not self.analyze_scenario(scenario_config, target_date=current_date):
                    day_verdict = False

            if not day_verdict:
                final_verdict = False
                self.log(f"XXX Day {current_date} FAILED XXX")
            else:
                self.log(f"VVV Day {current_date} PASSED VVV")

        self.log("\n========================================")
        if final_verdict:
            self.log("FINAL VERDICT: ALL DAYS PASSED")
        else:
            self.log("FINAL VERDICT: FAILURES DETECTED")
        self.log("========================================")

    def _check_run_day(self, test_config, reference_date=None):
        check_date = reference_date if reference_date else self.log_start_date
        py_weekday = check_date.weekday()
        current_netafim_day = (py_weekday + 2)
        if current_netafim_day > 7:
            current_netafim_day = 1

        day_name = check_date.strftime("%A")
        schedule_type = test_config.get('irrigationScheduleType', 'WeekDays')

        if schedule_type == 'IntervalDays':
            interval = test_config.get('intervalDays', 1)
            start_day = test_config.get('currentIntervalDay', 1)
            self.log(f"  [CHECK DAY] Date: {check_date.date()} | Mode: Interval (Every {interval}, Start day: {start_day})")
            if interval == 1:
                return True
            if (current_netafim_day - start_day) % interval == 0:
                self.log(f"  [CHECK DAY] Date: {check_date.date()} | Netafim day {current_netafim_day} is scheduled (start={start_day}, every={interval})")
                return True
            self.log(f"  [CHECK DAY] SKIP: Netafim day {current_netafim_day} not in interval (start={start_day}, every={interval})")
            return False

        allowed_days = test_config.get('run_days', [])
        if not allowed_days:
            return True

        if current_netafim_day in allowed_days:
            self.log(f"  [CHECK DAY] Success: Date {check_date.date()} ({day_name}) is allowed.")
            return True
        else:
            self.log(f"  [CHECK DAY] FAIL: Date {check_date.date()} ({day_name}/Id:{current_netafim_day}) NOT in {allowed_days}")
            return False

    def _has_valve_activity_on_date(self, target_date):
        """Returns True if any valve open/close events exist on the given date."""
        for event in self.events:
            evt_time = self._parse_time(event['time'])
            if evt_time and evt_time.date() == target_date and event.get('type') == 'valve':
                return True
        return False

    def analyze_scenario(self, test_config, target_date=None):
        """
        Runs logic for a SINGLE test scenario.
        Accepts target_date to force checking a specific day from the log.
        """
        start_time_str = test_config.get('start_Time', "00:00")
        if 'shifts_structure' in test_config and test_config.get('start_times'):
            start_time_str = test_config['start_times'][0]
        elif 'shifts_schedule' in test_config and test_config.get('shifts_schedule'):
            start_time_str = test_config['shifts_schedule'][0][0]

        if target_date:
            t_part = datetime.strptime(
                start_time_str,
                "%H:%M:%S" if len(start_time_str.split(':')) == 3 else "%H:%M"
            ).time()
            t_start_struct = datetime.combine(target_date, t_part)
        else:
            t_start_struct = self._parse_time(start_time_str)

        if not t_start_struct:
            self.log(f"Error parsing start time {start_time_str}")
            return False

        if not self._check_run_day(test_config, reference_date=t_start_struct):
            self.log(f"Skipping test '{test_config.get('testname')}' - Schedule not valid for {t_start_struct.date()}.")
            return True

        original_log_start = self.log_start_date
        if target_date:
            self.log_start_date = datetime.combine(target_date, datetime.min.time())

        try:
            if 'shifts_structure' in test_config:
                return self._analyze_compact_shifts_mode(test_config)
            if 'shifts_schedule' in test_config:
                return self._analyze_shifts(test_config)
            return self._analyze_regular_scenario(test_config)
        finally:
            if target_date:
                self.log_start_date = original_log_start

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _find_valve_event(self, v_id, action_kw, t_from, t_to):
        """Return first matching valve event within [t_from, t_to]."""
        for e in self.events:
            if e['type'] != 'valve' or e['id'] != v_id:
                continue
            if action_kw not in e['action']:
                continue
            et = self._parse_time(e['time'])
            if et and t_from <= et <= t_to:
                return e
        return None

    def _nearest_valve_event(self, v_id, action_kw, t_ref):
        """Return (event, diff_seconds) for the nearest matching event to t_ref."""
        best, best_diff = None, float('inf')
        for e in self.events:
            if e['type'] != 'valve' or e['id'] != v_id:
                continue
            if action_kw not in e['action']:
                continue
            et = self._parse_time(e['time'])
            if et:
                d = abs((et - t_ref).total_seconds())
                if d < best_diff:
                    best, best_diff = e, d
        return best, best_diff

    def _get_wm_delta(self, wm_id, open_event, close_event):
        """
        Calculate pulse delta for wm_id between two events using their wm_snapshot.
        Returns (start_count, end_count, delta) or None if snapshot missing.
        """
        snap_open  = open_event.get('wm_snapshot', {})
        snap_close = close_event.get('wm_snapshot', {})
        if wm_id not in snap_open or wm_id not in snap_close:
            return None
        start = snap_open[wm_id]
        end   = snap_close[wm_id]
        return start, end, end - start

    def _get_valve_pairs(self, v_id, t_start, t_end):
        """
        Return list of (open_event, close_event) pairs for v_id within [t_start, t_end].
        Pairs are matched in order: each open is paired with the next close.
        """
        opens, closes = [], []
        for e in self.events:
            if e['type'] != 'valve' or e['id'] != v_id:
                continue
            et = self._parse_time(e['time'])
            if not et or not (t_start <= et <= t_end):
                continue
            if 'open' in e['action']:
                opens.append((et, e))
            elif 'close' in e['action']:
                closes.append((et, e))
        pairs = []
        ci = 0
        for ot, oe in opens:
            while ci < len(closes) and closes[ci][0] <= ot:
                ci += 1
            if ci < len(closes):
                pairs.append((oe, closes[ci][1]))
                ci += 1
        return pairs

    def _check_valve_open(self, v_id, t_expected, grace_delta, label=""):
        """
        Check that valve v_id opens within grace of t_expected.
        Returns (passed:bool, event_or_None, diff_seconds).
        """
        t_from = t_expected - timedelta(seconds=30)
        t_to   = t_expected + grace_delta
        e = self._find_valve_event(v_id, 'open', t_from, t_to)
        if e:
            et   = self._parse_time(e['time'])
            diff = (et - t_expected).total_seconds()
            sign = '+' if diff >= 0 else ''
            self.log(f"       [PASS] V{v_id} open @ [{e['original_time']}] ({sign}{int(diff)}s) {label}")
            return True, e, diff
        nearest, nd = self._nearest_valve_event(v_id, 'open', t_expected)
        if nearest:
            et   = self._parse_time(nearest['time'])
            diff = (et - t_expected).total_seconds()
            sign = '+' if diff >= 0 else ''
            self.log(f"       [FAIL] V{v_id} open – nearest @ [{nearest['original_time']}] ({sign}{int(diff)}s, outside grace) {label}")
        else:
            self.log(f"       [FAIL] V{v_id} open – no event found in log {label}")
        return False, nearest, nd if nearest else 0

    def _check_valve_close(self, v_id, t_expected, grace_delta, label=""):
        """
        Check that valve v_id closes within grace of t_expected.
        Returns (passed:bool, event_or_None, diff_seconds).
        """
        t_from = t_expected - timedelta(seconds=30)
        t_to   = t_expected + grace_delta
        e = self._find_valve_event(v_id, 'close', t_from, t_to)
        if e:
            et   = self._parse_time(e['time'])
            diff = (et - t_expected).total_seconds()
            sign = '+' if diff >= 0 else ''
            self.log(f"       [PASS] V{v_id} close @ [{e['original_time']}] ({sign}{int(diff)}s) {label}")
            return True, e, diff
        nearest, nd = self._nearest_valve_event(v_id, 'close', t_expected)
        if nearest:
            et   = self._parse_time(nearest['time'])
            diff = (et - t_expected).total_seconds()
            sign = '+' if diff >= 0 else ''
            self.log(f"       [FAIL] V{v_id} close – nearest @ [{nearest['original_time']}] ({sign}{int(diff)}s, outside grace) {label}")
        else:
            self.log(f"       [FAIL] V{v_id} close – no event found in log {label}")
        return False, nearest, nd if nearest else 0

    def _check_wm_quantity(self, wm_id, open_event, close_event, expected, tolerance_pct, label=""):
        """
        Check wm_id pulse delta between open/close events is within tolerance.
        Returns passed:bool.
        """
        if open_event is None or close_event is None:
            self.log(f"       [FAIL] WM{wm_id} quantity – missing open/close event for delta {label}")
            return False
        result = self._get_wm_delta(wm_id, open_event, close_event)
        if result is None:
            self.log(f"       [FAIL] WM{wm_id} – no snapshot data in events {label}")
            return False
        start, end, delta = result
        tol = expected * tolerance_pct / 100.0
        lo  = expected - tol
        hi  = expected + tol
        rate = getattr(self, 'pulse_rate', None)
        liters_str  = f" = {delta   * rate:.1f}L" if rate else ""
        target_str  = f"{expected * rate:.1f}L" if rate else f"{expected} pulses"
        if lo <= delta <= hi:
            self.log(f"       [PASS] WM{wm_id} delta={delta}{liters_str} (start={start} end={end}) target={target_str}±{tolerance_pct}% {label}")
            return True
        else:
            self.log(f"       [FAIL] WM{wm_id} delta={delta}{liters_str} (start={start} end={end}) target={target_str}±{tolerance_pct}% {label}")
            return False

    def _print_summary(self, test_name, shift_results):
        """Print a clean summary table for the scenario."""
        total   = len(shift_results)
        passed  = sum(1 for r in shift_results if r)
        failed  = total - passed
        self.log(f"\n  ┌─────────────────────────────────────────┐")
        self.log(f"  │  SUMMARY: {test_name[:30]:<30} │")
        self.log(f"  │  Shifts: {total}  Passed: {passed}  Failed: {failed}{'': <10}│")
        self.log(f"  └─────────────────────────────────────────┘")
        overall = "✔ PASSED" if failed == 0 else "✘ FAILED"
        self.log(f"  >>> Result: {overall} <<<")
        return failed == 0

    # =========================================================================
    # MODE 1 — IRRIGATION ONLY
    # =========================================================================

    def _m1_analyze_time(self, test_name, shifts_structure, cycle_start, grace_delta):
        """Mode 1, unit=time: check valve open+close timing per shift."""
        shift_results = []
        current_shift_start = cycle_start

        for sh_idx, shift in enumerate(shifts_structure):
            duration       = self._parse_duration(shift.get('duration', "00:00:00"))
            current_valves = set(shift.get('valves', []))
            prev_valves    = set(shifts_structure[sh_idx - 1].get('valves', [])) if sh_idx > 0 else set()
            next_valves    = set(shifts_structure[sh_idx + 1].get('valves', [])) if sh_idx < len(shifts_structure) - 1 else set()
            valves_to_open  = current_valves - prev_valves
            valves_to_close = current_valves - next_valves
            current_shift_end = current_shift_start + duration

            self.log(f"\n  -- Shift #{sh_idx + 1} ({shift.get('duration')}) Valves:{sorted(current_valves)} --")
            self.log(f"     Window: {current_shift_start.strftime('%H:%M:%S')} -> {current_shift_end.strftime('%H:%M:%S')}")

            shift_passed = True
            self.log(f"     [CHECK 1] Valve Open:")
            for v_id in sorted(valves_to_open):
                ok, _, _ = self._check_valve_open(v_id, current_shift_start, grace_delta)
                if not ok:
                    shift_passed = False

            self.log(f"     [CHECK 2] Valve Close:")
            for v_id in sorted(valves_to_close):
                ok, _, _ = self._check_valve_close(v_id, current_shift_end, grace_delta)
                if not ok:
                    shift_passed = False

            shift_results.append(shift_passed)
            current_shift_start = current_shift_end

        return self._print_summary(test_name, shift_results)

    def _m1_analyze_quantity(self, test_name, shifts_structure, cycle_start, grace_delta, tolerance_pct):
        """Mode 1, unit=quantity: check valve open timing + WM1 delta per shift."""
        shift_results = []
        current_shift_start = cycle_start
        wm_id = 1  # Mode 1 always uses WM1

        for sh_idx, shift in enumerate(shifts_structure):
            duration        = self._parse_duration(shift.get('duration', "00:00:00"))
            current_valves  = set(shift.get('valves', []))
            expected_pulses = shift.get('expected_pulses', 0) or 0
            _rate = getattr(self, 'pulse_rate', None)
            _warn_rate = None
            if not expected_pulses:
                expected_liters = shift.get('expected_liters', 0) or 0
                if expected_liters and _rate:
                    expected_pulses = expected_liters / _rate
                elif expected_liters and not _rate:
                    _warn_rate = expected_liters
            prev_valves     = set(shifts_structure[sh_idx - 1].get('valves', [])) if sh_idx > 0 else set()
            next_valves     = set(shifts_structure[sh_idx + 1].get('valves', [])) if sh_idx < len(shifts_structure) - 1 else set()
            valves_to_open  = current_valves - prev_valves
            valves_to_close = current_valves - next_valves
            current_shift_end = current_shift_start + duration

            self.log(f"\n  -- Shift #{sh_idx + 1} ({shift.get('duration')}) Valves:{sorted(current_valves)} --")
            self.log(f"     Window: {current_shift_start.strftime('%H:%M:%S')} -> {current_shift_end.strftime('%H:%M:%S')}")
            if _warn_rate:
                self.log(f"     [WARN] expected_liters={_warn_rate} but rate=null in JSON – set rate to enable quantity check")

            shift_passed = True
            open_events  = {}
            self.log(f"     [CHECK 1] Valve Open:")
            for v_id in sorted(valves_to_open):
                ok, evt, _ = self._check_valve_open(v_id, current_shift_start, grace_delta)
                if not ok:
                    shift_passed = False
                open_events[v_id] = evt

            # In quantity mode: valve close timing is not checked – only WM quantity matters
            close_events = {}
            for v_id in sorted(valves_to_close):
                # Search with a wide window – valve closes when quantity is reached, not at a fixed time
                t_search_from = current_shift_start - grace_delta
                t_search_to   = current_shift_end + timedelta(hours=2)
                close_evt = self._find_valve_event(v_id, 'close', t_search_from, t_search_to)
                if close_evt:
                    self.log(f"       [INFO] V{v_id} close @ [{close_evt['original_time']}] (quantity mode – timing not checked)")
                else:
                    self.log(f"       [FAIL] V{v_id} close – no event found in log")
                    shift_passed = False
                close_events[v_id] = close_evt

            # WM1 quantity: determine open_ref and close_ref for delta measurement
            if expected_pulses > 0:
                # open_ref: first new valve that opens this shift
                # fallback: close of the valve that left the previous shift (transition marker)
                rep_open_v = sorted(valves_to_open)[0] if valves_to_open else None
                open_evt   = open_events.get(rep_open_v) if rep_open_v else None

                if open_evt is None and sh_idx > 0:
                    # Use close of valve that dropped out from prev shift → current shift
                    # Use prev shift duration as search window (not grace_delta) so transition
                    # is always found regardless of how small grace_delta is
                    leaving_valves = prev_valves - current_valves
                    if leaving_valves:
                        leave_v = sorted(leaving_valves)[0]
                        prev_duration = self._parse_duration(shifts_structure[sh_idx - 1].get('duration', '00:00:00'))
                        t_trans_from  = current_shift_start - prev_duration
                        t_trans_to    = current_shift_end
                        open_evt = self._find_valve_event(leave_v, 'close', t_trans_from, t_trans_to)
                        if open_evt:
                            self.log(f"       [INFO] Shift transition: V{leave_v} close @ [{open_evt['original_time']}] used as WM start-ref")

                # close_ref: prefer a valve that closes this shift;
                # fallback: first new valve opening of next shift (shift transition signal)
                close_evt = None
                if valves_to_close:
                    rep_close_v = sorted(valves_to_close)[0]
                    close_evt = close_events.get(rep_close_v)
                elif sh_idx < len(shifts_structure) - 1:
                    # Use next shift's first new valve open as transition marker
                    next_shift_valves = set(shifts_structure[sh_idx + 1].get('valves', []))
                    next_new_valves   = next_shift_valves - current_valves
                    if next_new_valves:
                        next_v = sorted(next_new_valves)[0]
                        next_shift_start = current_shift_end
                        next_shift_end   = next_shift_start + self._parse_duration(
                            shifts_structure[sh_idx + 1].get('duration', '00:00:00'))
                        close_evt = self._find_valve_event(next_v, 'open',
                                                           next_shift_start - grace_delta,
                                                           next_shift_end + grace_delta)
                        if close_evt:
                            self.log(f"       [INFO] Shift transition detected: V{next_v} open @ [{close_evt['original_time']}] used as WM end-ref")

                if open_evt and close_evt:
                    ok = self._check_wm_quantity(wm_id, open_evt, close_evt,
                                                 expected_pulses, tolerance_pct,
                                                 f"(shift #{sh_idx+1})")
                    if not ok:
                        shift_passed = False
                else:
                    self.log(f"       [INFO] Shift #{sh_idx+1}: cannot determine WM delta bounds – skipping")

            shift_results.append(shift_passed)
            # In quantity mode: advance current_shift_start to the ACTUAL last close event
            # of this shift (not the theoretical config time). This ensures the next shift's
            # open-event search is anchored to the real transition, not a fixed duration.
            actual_transition = None
            for v_id in sorted(valves_to_close):
                evt = close_events.get(v_id)
                if evt:
                    t = self._parse_time(evt['time'])
                    if t and (actual_transition is None or t > actual_transition):
                        actual_transition = t
            if actual_transition:
                self.log(f"       [INFO] Shift transition: actual close time {actual_transition.strftime('%H:%M:%S')} → used as next shift anchor")
                current_shift_start = actual_transition
            else:
                current_shift_start = current_shift_end

        return self._print_summary(test_name, shift_results)

    # =========================================================================
    # MODE 2 — IRRIGATION (per-valve WM mapping)
    # =========================================================================

    def _m2_analyze_irrigation(self, test_name, shifts_structure, cycle_start, grace_delta, unit, tolerance_pct):
        """
        Mode 2 irrigation: same logic as Mode 1 but each Valve N uses WM N.
        """
        shift_results = []
        current_shift_start = cycle_start

        for sh_idx, shift in enumerate(shifts_structure):
            duration        = self._parse_duration(shift.get('duration', "00:00:00"))
            current_valves  = set(shift.get('valves', []))
            expected_pulses = shift.get('expected_pulses', 0) or 0
            _rate = getattr(self, 'pulse_rate', None)
            _warn_rate = None
            if not expected_pulses:
                expected_liters = shift.get('expected_liters', 0) or 0
                if expected_liters and _rate:
                    expected_pulses = expected_liters / _rate
                elif expected_liters and not _rate:
                    _warn_rate = expected_liters
            prev_valves     = set(shifts_structure[sh_idx - 1].get('valves', [])) if sh_idx > 0 else set()
            next_valves     = set(shifts_structure[sh_idx + 1].get('valves', [])) if sh_idx < len(shifts_structure) - 1 else set()
            valves_to_open  = current_valves - prev_valves
            valves_to_close = current_valves - next_valves
            current_shift_end = current_shift_start + duration

            self.log(f"\n  -- Shift #{sh_idx + 1} ({shift.get('duration')}) Valves:{sorted(current_valves)} --")
            self.log(f"     Window: {current_shift_start.strftime('%H:%M:%S')} -> {current_shift_end.strftime('%H:%M:%S')}")
            if _warn_rate:
                self.log(f"     [WARN] expected_liters={_warn_rate} but rate=null in JSON – set rate to enable quantity check")

            shift_passed = True
            open_events  = {}
            close_events = {}

            self.log(f"     [CHECK 1] Valve Open:")
            for v_id in sorted(valves_to_open):
                ok, evt, _ = self._check_valve_open(v_id, current_shift_start, grace_delta)
                if not ok:
                    shift_passed = False
                open_events[v_id] = evt

            self.log(f"     [CHECK 2] Valve Close{' + WM Quantity (timing not checked)' if unit=='quantity' else ''}:")
            for v_id in sorted(valves_to_close):
                if unit == 'quantity':
                    # In quantity mode: timing of close is not validated – valve closes when quantity is reached
                    t_search_from = current_shift_start - grace_delta
                    t_search_to   = current_shift_end + timedelta(hours=2)
                    evt = self._find_valve_event(v_id, 'close', t_search_from, t_search_to)
                    if evt:
                        self.log(f"       [INFO] V{v_id} close @ [{evt['original_time']}] (quantity mode – timing not checked)")
                    else:
                        self.log(f"       [FAIL] V{v_id} close – no event found in log")
                        shift_passed = False
                else:
                    ok, evt, _ = self._check_valve_close(v_id, current_shift_end, grace_delta)
                    if not ok:
                        shift_passed = False
                close_events[v_id] = evt

                if unit == 'quantity' and expected_pulses > 0:
                    wm_id = v_id  # Valve N → WM N
                    open_evt = open_events.get(v_id)
                    ok_q = self._check_wm_quantity(wm_id, open_evt, evt,
                                                   expected_pulses, tolerance_pct,
                                                   f"V{v_id}→WM{wm_id} shift#{sh_idx+1}")
                    if not ok_q:
                        shift_passed = False

            shift_results.append(shift_passed)
            current_shift_start = current_shift_end

        return self._print_summary(test_name, shift_results)

    # =========================================================================
    # MODE 2 — FERTIGATION ENGINES
    # =========================================================================

    def _m2_bulck_time(self, ch, t_program_start, t_program_end, grace_delta):
        """
        BULCK time: fertigation valve should open near program start and
        close near program end.
        """
        v_id   = ch.get('channel')
        wm_id  = ch.get('watermeter_id', v_id)
        dur_str = ch.get('duration', None)
        self.log(f"\n     [FERTIGATION] Ch{v_id} BULCK/TIME")

        ok_o, open_evt, _ = self._check_valve_open(v_id, t_program_start, grace_delta, f"ch{v_id}")
        t_close_expected  = (t_program_start + self._parse_duration(dur_str)
                             if dur_str else t_program_end)
        ok_c, close_evt, _ = self._check_valve_close(v_id, t_close_expected, grace_delta, f"ch{v_id}")
        return ok_o and ok_c

    def _m2_bulck_quantity(self, ch, t_program_start, t_program_end, grace_delta, tolerance_pct):
        """
        BULCK quantity: fertigation valve should open, accumulate expected_pulses, then close.
        """
        v_id          = ch.get('channel')
        wm_id         = ch.get('watermeter_id', v_id)
        expected      = ch.get('expected_pulses', 0) or 0
        _rate = getattr(self, 'pulse_rate', None)
        if not expected:
            expected_liters = ch.get('expected_liters', 0) or 0
            if expected_liters and _rate:
                expected = expected_liters / _rate
            elif expected_liters and not _rate:
                self.log(f"       [WARN] Ch{v_id}: expected_liters={expected_liters} but rate=null – set rate to enable quantity check")
                return True
        self.log(f"\n     [FERTIGATION] Ch{v_id} BULCK/QUANTITY target={expected}")

        ok_o, open_evt, _ = self._check_valve_open(v_id, t_program_start, grace_delta, f"ch{v_id}")
        # Close can happen anywhere inside program window
        t_from = t_program_start
        t_to   = t_program_end + grace_delta
        close_evt = self._find_valve_event(v_id, 'close', t_from, t_to)
        if close_evt:
            self.log(f"       [INFO] Ch{v_id} closed @ {close_evt['original_time']}")
        else:
            self.log(f"       [FAIL] Ch{v_id} – no close event found")
            return False
        ok_q = self._check_wm_quantity(wm_id, open_evt, close_evt, expected, tolerance_pct, f"ch{v_id}")
        return ok_o and ok_q

    def _m2_spread_time(self, ch, t_program_start, t_program_end, grace_delta):
        """
        SPREAD time: fertigation valve cycles ON/OFF repeatedly during program.
        Checks: correct on_seconds, off_seconds, and cycling during entire window.
        """
        v_id       = ch.get('channel')
        on_sec     = ch.get('on_seconds', 5)
        off_sec    = ch.get('off_seconds', 5)
        tolerance  = grace_delta.total_seconds()
        self.log(f"\n     [FERTIGATION] Ch{v_id} SPREAD/TIME on={on_sec}s off={off_sec}s")

        pairs = self._get_valve_pairs(v_id, t_program_start, t_program_end + grace_delta)
        if not pairs:
            self.log(f"       [FAIL] Ch{v_id} – no open/close pairs found in program window")
            return False

        self.log(f"       Found {len(pairs)} cycle(s)")
        all_ok = True
        for idx, (oe, ce) in enumerate(pairs):
            ot = self._parse_time(oe['time'])
            ct = self._parse_time(ce['time'])
            ot_str = oe.get('original_time', '')
            ct_str = ce.get('original_time', '')
            if ot and ct:
                on_actual = (ct - ot).total_seconds()
                if abs(on_actual - on_sec) <= tolerance:
                    self.log(f"       [{ot_str}] [PASS] Cycle {idx+1}: ON={on_actual:.1f}s (expected {on_sec}s)")
                else:
                    self.log(f"       [{ot_str}] [FAIL] Cycle {idx+1}: ON={on_actual:.1f}s (expected {on_sec}s ±{tolerance}s)")
                    all_ok = False

            # Check OFF gap to next cycle
            if idx + 1 < len(pairs):
                next_oe = pairs[idx + 1][0]
                nt = self._parse_time(next_oe['time'])
                if ct and nt:
                    off_actual = (nt - ct).total_seconds()
                    if abs(off_actual - off_sec) <= tolerance:
                        self.log(f"       [{ct_str}] [PASS] Cycle {idx+1} OFF gap={off_actual:.1f}s (expected {off_sec}s)")
                    else:
                        self.log(f"       [{ct_str}] [FAIL] Cycle {idx+1} OFF gap={off_actual:.1f}s (expected {off_sec}s ±{tolerance}s)")
                        all_ok = False

        # Check that cycling spans the entire program
        first_open = self._parse_time(pairs[0][0]['time'])
        last_close = self._parse_time(pairs[-1][1]['time'])
        last_close_str = pairs[-1][1].get('original_time', '')
        if first_open and last_close:
            span = (last_close - first_open).total_seconds()
            expected_span = (t_program_end - t_program_start).total_seconds()
            if span >= expected_span - tolerance:
                self.log(f"       [{last_close_str}] [PASS] Cycling span={span:.0f}s covers program {expected_span:.0f}s")
            else:
                self.log(f"       [{last_close_str}] [FAIL] Cycling span={span:.0f}s < program {expected_span:.0f}s")
                all_ok = False

        return all_ok

    def _m2_spread_quantity(self, ch, t_program_start, t_program_end, grace_delta, tolerance_pct):
        """SPREAD quantity – placeholder for future implementation."""
        v_id = ch.get('channel')
        self.log(f"\n     [FERTIGATION] Ch{v_id} SPREAD/QUANTITY – not yet implemented (SKIP)")
        return True  # treat as non-blocking

    def _m2_proportional(self, ch, t_program_start, t_program_end, grace_delta, tolerance_pct):
        """
        PROPORTIONAL: fertigation valve opens every TRIGGER_LITERS of WM1 water,
        injects expected_pulses on its own WM, then closes.
        Constants (hardcoded): MAIN_WM_ID=1, PULSE_TO_LITER=1.0, TRIGGER_LITERS=2000
        """
        MAIN_WM_ID     = 1
        PULSE_TO_LITER = 1.0

        v_id           = ch.get('channel')
        wm_id          = ch.get('watermeter_id', v_id)
        dose           = ch.get('expected_pulses', 0) or 0
        _rate = getattr(self, 'pulse_rate', None)
        if not dose:
            dose_liters = ch.get('expected_liters', 0) or 0
            if dose_liters and _rate:
                dose = dose_liters / _rate
            elif dose_liters and not _rate:
                self.log(f"       [WARN] Ch{v_id}: expected_liters={dose_liters} but rate=null – set rate to enable quantity check")
                return True
        TRIGGER_LITERS = 2000  # liters per fertigation cycle (fixed)

        self.log(f"\n     [FERTIGATION] Ch{v_id} PROPORTIONAL | WM{MAIN_WM_ID} trigger={TRIGGER_LITERS}L | dose={dose} pulses")

        # --- Find WM1 start and end snapshots within program window ---
        wm1_start = None
        wm1_end   = None
        for e in self.events:
            ft = e.get('full_time')
            if ft and t_program_start <= ft <= t_program_end + grace_delta:
                snap = e.get('wm_snapshot', {})
                if MAIN_WM_ID in snap:
                    if wm1_start is None:
                        wm1_start = snap[MAIN_WM_ID]
                    wm1_end = snap[MAIN_WM_ID]

        if wm1_start is None or wm1_end is None:
            self.log(f"       [FAIL] Could not determine WM{MAIN_WM_ID} pulses during program")
            return False

        wm1_delta    = wm1_end - wm1_start
        total_liters = wm1_delta * PULSE_TO_LITER
        expected_cycles = int(total_liters // TRIGGER_LITERS)

        self.log(f"       WM{MAIN_WM_ID}: start={wm1_start} end={wm1_end} → delta={wm1_delta} pulses = {total_liters:.1f}L")
        self.log(f"       Expected cycles: {total_liters:.0f}L ÷ {TRIGGER_LITERS}L = {expected_cycles}")

        if expected_cycles == 0:
            self.log(f"       [FAIL] Not enough WM{MAIN_WM_ID} water for even 1 fertigation cycle")
            return False

        # --- Get actual fertigation cycles (valve open/close pairs) ---
        pairs = self._get_valve_pairs(v_id, t_program_start, t_program_end + grace_delta)
        actual_cycles = len(pairs)
        tol = max(1, round(expected_cycles * tolerance_pct / 100))

        all_ok = True

        # --- Per-cycle validation ---
        for idx, (oe, ce) in enumerate(pairs):
            ot_str = oe.get('original_time', '')
            ct_str = ce.get('original_time', '')
            self.log(f"\n       Cycle {idx+1}/{actual_cycles}:")
            self.log(f"       [{ot_str}]  Open  Ch{v_id}")
            self.log(f"       [{ct_str}]  Close Ch{v_id}")

            # Check dose (WM pulses between open and close)
            result = self._get_wm_delta(wm_id, oe, ce)
            if result is None:
                self.log(f"                   [FAIL] WM{wm_id} – no snapshot data for this cycle")
                all_ok = False
            else:
                start_p, end_p, delta_p = result
                tol_dose = dose * tolerance_pct / 100.0
                lo, hi = dose - tol_dose, dose + tol_dose
                status = "[PASS]" if lo <= delta_p <= hi else "[FAIL]"
                rate = getattr(self, 'pulse_rate', None)
                liters_str = f" = {delta_p * rate:.1f}L" if rate else ""
                dose_str   = f"{dose * rate:.1f}L" if rate else f"{dose} pulses"
                self.log(f"                   WM{wm_id} delta={delta_p}{liters_str} (start={start_p} end={end_p}) target={dose_str}±{tolerance_pct}% → {status}")
                if status == "[FAIL]":
                    all_ok = False

            # Check that WM1 accumulated the right amount before this cycle opened
            ot_full = oe.get('full_time')
            if ot_full:
                wm1_at_open = None
                for e in self.events:
                    ft = e.get('full_time')
                    if ft and t_program_start <= ft <= ot_full:
                        snap = e.get('wm_snapshot', {})
                        if MAIN_WM_ID in snap:
                            wm1_at_open = snap[MAIN_WM_ID]
                if wm1_at_open is not None:
                    liters_at_open = (wm1_at_open - wm1_start) * PULSE_TO_LITER
                    expected_liters_at_open = idx * TRIGGER_LITERS
                    tol_liters = TRIGGER_LITERS * tolerance_pct / 100.0
                    diff = liters_at_open - expected_liters_at_open
                    status = "[PASS]" if abs(diff) <= tol_liters else "[FAIL]"
                    self.log(f"                   WM{MAIN_WM_ID} at open={liters_at_open:.0f}L (expected ~{expected_liters_at_open}L, diff={diff:+.0f}L) → {status}")
                    if status == "[FAIL]":
                        all_ok = False

        # --- Summary ---
        self.log(f"")
        if abs(actual_cycles - expected_cycles) <= tol:
            self.log(f"       [PASS] Total cycles: actual={actual_cycles} expected={expected_cycles} (±{tol})")
        else:
            self.log(f"       [FAIL] Total cycles: actual={actual_cycles} expected={expected_cycles} (±{tol})")
            all_ok = False

        return all_ok

    # =========================================================================
    # DISPATCHER
    # =========================================================================

    def _analyze_compact_shifts_mode(self, test_config):
        """
        Main dispatcher for shifts_structure format.
        Routes to Mode 1 or Mode 2 sub-analyzers based on JSON 'mode' field.
        """
        test_name       = test_config.get('testname', 'Combined Test')
        mode            = test_config.get('mode', 1)            # 1 or 2
        unit            = test_config.get('unit', 'time')       # 'time' or 'quantity'
        start_times     = test_config.get('start_times', [])
        shifts_structure = test_config.get('shifts_structure', [])
        grace_time_str  = test_config.get('grace_Time', "00:01:00")
        grace_delta     = self._parse_duration(grace_time_str)
        tolerance_pct   = test_config.get('pulse_tolerance_pct', 5)
        self.pulse_rate = test_config.get('rate', None)
        fertilization   = test_config.get('fertilization', {})
        fert_active     = fertilization.get('active', False) and (mode == 2)
        fert_channels   = [ch for ch in fertilization.get('channels', []) if ch.get('active', True)]

        self.log(f"\n=========================================")
        self.log(f"--- {test_name} | Mode {mode} | unit={unit} | grace={grace_time_str} | tol={tolerance_pct}% ---")
        self.log(f"=========================================")

        all_passed = True

        for st_idx, start_time_str in enumerate(start_times):
            cycle_start = self._parse_time(start_time_str)
            if not cycle_start:
                self.log(f"  [ERROR] Bad Start Time: {start_time_str}")
                all_passed = False
                continue

            # Calculate total program end (sum of all shift durations)
            total_duration = sum([self._parse_duration(s.get('duration', '00:00:00'))
                                  for s in shifts_structure], timedelta())
            cycle_end = cycle_start + total_duration

            # Find actual first/last valve event in the cycle window
            # In quantity mode: use only a small 60s pre-buffer so we don't capture
            # events from the previous program run. Extend search_to widely since
            # the program runs until quantity is reached (not a fixed duration).
            if unit == 'quantity':
                search_from = cycle_start - timedelta(seconds=60)
                search_to   = cycle_end + timedelta(hours=3)
            else:
                search_from = cycle_start - grace_delta
                search_to   = cycle_end + grace_delta
            valve_events_in_window = [
                e for e in self.events
                if e['type'] == 'valve' and
                   search_from <= e['full_time'] <= search_to
            ]
            # actual_start = earliest OPEN event (a program starts with an open, not a close)
            open_events_in_window = [e for e in valve_events_in_window if e.get('action') == 'open']
            if open_events_in_window:
                actual_start = min(e['full_time'] for e in open_events_in_window)
            elif valve_events_in_window:
                actual_start = min(e['full_time'] for e in valve_events_in_window)
            else:
                actual_start = None

            if valve_events_in_window:
                actual_end   = max(e['full_time'] for e in valve_events_in_window)
                actual_str = f"{actual_start.strftime('%H:%M:%S')} → {actual_end.strftime('%H:%M:%S')}"
            else:
                actual_str = "no events found"

            self.log(f"\n>>> Cycle #{st_idx + 1} <<<")
            self.log(f"    Expected: {start_time_str} → {cycle_end.strftime('%H:%M:%S')}")
            self.log(f"    Actual:   {actual_str}")

            # ---- IRRIGATION ANALYSIS ----
            if mode == 1:
                if unit == 'time':
                    ok = self._m1_analyze_time(test_name, shifts_structure, cycle_start, grace_delta)
                else:
                    ok = self._m1_analyze_quantity(test_name, shifts_structure, cycle_start,
                                                   grace_delta, tolerance_pct)
            else:  # mode == 2
                ok = self._m2_analyze_irrigation(test_name, shifts_structure, cycle_start,
                                                 grace_delta, unit, tolerance_pct)

            if not ok:
                all_passed = False

            # ---- FERTIGATION ANALYSIS (Mode 2 only) ----
            if fert_active:
                self.log(f"\n--- Fertigation Analysis | {len(fert_channels)} active channel(s) ---")
                for ch in fert_channels:
                    fert_type = (ch.get('mode') or fertilization.get('mode') or 'bulck').lower()
                    fert_unit = (ch.get('unit') or 'quantity').lower()
                    v_id      = ch.get('channel', '?')
                    self.log(f"\n  Channel {v_id}: mode={fert_type} unit={fert_unit}")

                    if fert_type == 'bulck':
                        if fert_unit == 'time':
                            ok_f = self._m2_bulck_time(ch, cycle_start, cycle_end, grace_delta)
                        else:
                            ok_f = self._m2_bulck_quantity(ch, cycle_start, cycle_end,
                                                           grace_delta, tolerance_pct)
                    elif fert_type == 'spread':
                        if fert_unit == 'time':
                            ok_f = self._m2_spread_time(ch, cycle_start, cycle_end, grace_delta)
                        else:
                            ok_f = self._m2_spread_quantity(ch, cycle_start, cycle_end,
                                                            grace_delta, tolerance_pct)
                    elif fert_type == 'proportional':
                        ok_f = self._m2_proportional(ch, cycle_start, cycle_end,
                                                     grace_delta, tolerance_pct)
                    else:
                        self.log(f"     [WARN] Unknown fertigation type '{fert_type}' – skipping")
                        ok_f = True

                    if not ok_f:
                        all_passed = False

        return all_passed


    def _analyze_shifts(self, test_config):
        test_name = test_config.get('testname', 'Unknown Test')
        shifts = test_config.get('shifts_schedule', [])
        wm_id = test_config.get('watermeter', 1)
        grace_time_str = test_config.get('grace_Time', "00:05")
        grace_delta = self._parse_duration(grace_time_str)

        self.log(f"Test Name: {test_name} (Multi-Shift Mode)")

        current_pass = True
        prev_valves = set()

        for i, shift in enumerate(shifts):
            s_start_str, s_end_str, s_valves_list, s_amount = shift
            s_valves = set(s_valves_list)

            t_start = self._parse_time(s_start_str)
            t_end = self._parse_time(s_end_str)

            next_valves = set()
            if i + 1 < len(shifts):
                next_valves = set(shifts[i + 1][2])

            self.log(f"  >>> Shift {i + 1}: {s_start_str} -> {s_end_str} | Active: {list(s_valves)}")

            valves_to_open = s_valves - prev_valves
            for v_id in valves_to_open:
                found = None
                w_start = t_start - timedelta(seconds=30)
                w_end = t_start + grace_delta
                for e in self.events:
                    if e['type'] == 'valve' and e['id'] == v_id and 'open' in e['action']:
                        et = self._parse_time(e['time'])
                        if not et:
                            continue
                        et_full = et.replace(year=t_start.year, month=t_start.month, day=t_start.day)
                        if w_start <= et_full <= w_end:
                            found = e
                            break
                if found:
                    self.log(f"    [PASS] Valve {v_id} opened at {found['time']}")
                else:
                    self.log(f"    [FAIL] Valve {v_id} failed to open at shift start.")
                    current_pass = False

            if s_amount > 0:
                w_start = t_start - timedelta(seconds=5)
                w_end = t_end + timedelta(seconds=5)
                candidates = []
                for e in self.events:
                    if e['type'] == 'wm' and e['id'] == wm_id and 'count' in e:
                        et = self._parse_time(e['time'])
                        if not et:
                            continue
                        et_full = et.replace(year=t_start.year, month=t_start.month, day=t_start.day)
                        if w_start <= et_full <= w_end:
                            candidates.append((et_full, e['count']))
                if candidates:
                    best = min(candidates, key=lambda x: abs((x[0] - t_end).total_seconds()))
                    total_pulses = best[1]
                    max_a = s_amount * 1.05
                    if total_pulses < s_amount:
                        self.log(f"    [FAIL] WM: {total_pulses} < {s_amount} (Target)")
                        current_pass = False
                    elif total_pulses > max_a:
                        self.log(f"    [FAIL] WM: {total_pulses} > {max_a:.1f} (Target + 5%)")
                        current_pass = False
                    else:
                        self.log(f"    [PASS] WM: {total_pulses} (Target {s_amount}) [OK]")
                else:
                    self.log(f"    [FAIL] No WM reading for shift.")
                    current_pass = False

            valves_to_close = s_valves - next_valves
            for v_id in valves_to_close:
                found = None
                w_start = t_end - timedelta(seconds=10)
                w_end = t_end + grace_delta
                for e in self.events:
                    if e['type'] == 'valve' and e['id'] == v_id and 'close' in e['action']:
                        et = self._parse_time(e['time'])
                        if not et:
                            continue
                        et_full = et.replace(year=t_start.year, month=t_start.month, day=t_start.day)
                        if w_start <= et_full <= w_end:
                            found = e
                            break
                if found:
                    self.log(f"    [PASS] Valve {v_id} closed at {found['time']}")
                else:
                    self.log(f"    [FAIL] Valve {v_id} failed to close at shift end.")
                    current_pass = False

            prev_valves = s_valves

        return current_pass

    def _analyze_regular_scenario(self, test_config):
        test_name = test_config.get('testname', 'Unknown Test')

        if not self._check_run_day(test_config):
            self.log("Skipping test or marking Fail due to wrong day.")

        start_time_str = test_config.get('start_Time', "00:00")
        end_time_str = test_config.get('end_Time', None)
        grace_time_str = test_config.get('grace_Time', "00:00")
        target_valves = test_config.get('Valves', [])
        if not isinstance(target_valves, list):
            target_valves = []

        raw_amount = test_config.get('Amount')
        target_amount = raw_amount if raw_amount is not None else 0
        wm_id = test_config.get('watermeter', 1)

        self.log(f"Test Name: {test_name}")
        self.log(f"Active Valves: {target_valves}")

        is_quantity_mode = target_amount > 0
        mode_str = "Quantity" if is_quantity_mode else "Time"
        self.log(f"Test Mode: {mode_str}")

        t_start = self._parse_time(start_time_str)
        t_end = self._parse_time(end_time_str) if end_time_str else None
        grace_delta = self._parse_duration(grace_time_str)

        if not t_start:
            self.log("[ERROR] Invalid Start Time.")
            return False

        if not t_end:
            t_end = t_start + timedelta(hours=2)

        search_start_buffer = timedelta(seconds=30)
        scenario_start_limit = t_start - search_start_buffer
        scenario_end_limit = t_end + grace_delta

        if scenario_end_limit < scenario_start_limit:
            scenario_end_limit += timedelta(days=1)

        self.log(f"Strict Time Window: {scenario_start_limit.strftime('%H:%M:%S')} -> {scenario_end_limit.strftime('%H:%M:%S')}")

        current_pass = True

        # STEP 1: Valve Start Check
        self.log("  [CHECK 1] Valve Start Analysis...")
        for v_id in target_valves:
            found_valid = False
            for event in self.events:
                evt_time = self._parse_time(event['time'])
                if not evt_time:
                    continue
                evt_time_full = evt_time.replace(year=t_start.year, month=t_start.month, day=t_start.day)
                if not (scenario_start_limit <= evt_time_full <= scenario_end_limit):
                    continue
                if event['type'] == 'valve' and event['id'] == v_id and ('open' in event['action']):
                    diff = abs((evt_time_full - t_start).total_seconds())
                    if diff <= grace_delta.total_seconds() + 30:
                        self.log(f"    [PASS] Valve {v_id} opened at {event['time']}")
                        found_valid = True
                        break
            if not found_valid:
                self.log(f"    [FAIL] Valve {v_id} failed to open.")
                current_pass = False

        # STEP 2: Water Meter Analysis
        self.log("  [CHECK 2] Water Meter Analysis...")
        wm_candidates = []
        for event in self.events:
            evt_time = self._parse_time(event['time'])
            if not evt_time:
                continue
            evt_time_full = evt_time.replace(year=t_start.year, month=t_start.month, day=t_start.day)
            if scenario_start_limit <= evt_time_full <= scenario_end_limit:
                if event['type'] == 'wm' and event['id'] == wm_id:
                    if 'count' in event and event['count'] is not None:
                        wm_candidates.append((evt_time_full, event['count']))

        total_pulses = 0
        if wm_candidates:
            if t_end:
                best_candidate = min(wm_candidates, key=lambda x: abs((x[0] - t_end).total_seconds()))
            else:
                best_candidate = wm_candidates[-1]
            total_pulses = best_candidate[1]
            best_time_str = best_candidate[0].strftime("%H:%M:%S")
            self.log(f"    Selected Reading: {total_pulses} (at {best_time_str} - closest to end time)")
        else:
            self.log("    No WM readings found within scenario time window.")

        if is_quantity_mode:
            max_allowed = target_amount * 1.05
            if total_pulses < target_amount:
                self.log(f"    [FAIL] Quantity Low: {total_pulses} < {target_amount} (Target)")
                current_pass = False
            elif total_pulses > max_allowed:
                self.log(f"    [FAIL] Quantity High: {total_pulses} > {max_allowed:.1f} (Target + 5%)")
                current_pass = False
            else:
                self.log(f"    [PASS] Quantity Target Reached ({total_pulses}) [Target <= Q <= Target+5%]")
        else:
            self.log(f"    [INFO] (Time Mode) Pulses counted: {total_pulses}")

        # STEP 3: Valve Close Check
        self.log("  [CHECK 3] Valve Close Analysis...")
        for v_id in target_valves:
            found_valid = False
            found_any = False
            for event in self.events:
                evt_time = self._parse_time(event['time'])
                if not evt_time:
                    continue
                evt_time_full = evt_time.replace(year=t_start.year, month=t_start.month, day=t_start.day)
                if not (scenario_start_limit <= evt_time_full <= scenario_end_limit):
                    continue
                if event['type'] == 'valve' and event['id'] == v_id and ('close' in event['action']):
                    found_any = True
                    if is_quantity_mode:
                        self.log(f"    [PASS] Valve {v_id} closed at {event['time']}")
                        found_valid = True
                        break
                    else:
                        diff = abs((evt_time_full - t_end).total_seconds())
                        if diff <= grace_delta.total_seconds():
                            self.log(f"    [PASS] Valve {v_id} closed at {event['time']} (Diff: {diff}s)")
                            found_valid = True
                            break
            if not found_valid:
                current_pass = False
                if is_quantity_mode:
                    self.log(f"    [FAIL] Valve {v_id} did not close.")
                else:
                    if found_any:
                        self.log(f"    [FAIL] Valve {v_id} closed but NOT at expected time ({end_time_str}).")
                    else:
                        self.log(f"    [FAIL] Valve {v_id} did not close.")

        return current_pass


class FlexTesterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FLEX Tester Controller")
        self.root.geometry("1000x700")

        timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S")
        self._logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FLEX_LOGS")
        os.makedirs(self._logs_dir, exist_ok=True)
        self.log_file_path = os.path.join(self._logs_dir, f"terminal_log_{timestamp_str}.txt")
        self.current_log_day = datetime.now().day

        try:
            with open(self.log_file_path, "w") as f:
                f.write(f"--- Log Started: {time.ctime()} ---\n")
        except Exception as e:
            print(f"Error creating log file: {e}")

        self.serial_port = None
        self.is_connected = False
        self.read_thread = None
        self.stop_read = False
        self.buffer_1 = ""

        self.cli_log_file_path = None

        self.serial_port_2 = None
        self.is_connected_2 = False
        self.read_thread_2 = None
        self.stop_read_2 = False
        self.buffer_2 = ""
        self.init_response_event = threading.Event()

        # WM pulse graph data
        self.wm_pulse_data = {i: [] for i in range(1, 6)}   # {wm_id: [(datetime, 0/1)]}
        self.wm_pulse_state = {i: 0 for i in range(1, 6)}
        self.wm_active = {i: False for i in range(1, 6)}
        self.wm_after_ids = {i: None for i in range(1, 6)}
        self._rate_debounce_ids = {}

        # Auto CSV – opened when first WM starts, closed at midnight or app close
        self._wm_csv_file   = None
        self._wm_csv_writer = None
        self._wm_csv_path   = None
        self._wm_csv_date   = None   # date the file was opened for midnight-rollover check
        self._graph_refresh_id = None
        self._all_stopped_time = None
        self.wm_colors = {1: 'blue', 2: 'red', 3: 'green', 4: 'darkorange', 5: 'purple'}
        self.wm_offsets = {1: 0.0, 2: 1.5, 3: 3.0, 4: 4.5, 5: 6.0}

        style = ttk.Style()
        style.configure("TButton", padding=6, relief="flat", background="#ccc")
        style.configure("TLabel", padding=6)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tab1 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab1, text="Main Controller")
        self.setup_tab1(self.tab1)

        self.tab2 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab2, text="FLEX CLI")
        self.setup_tab2(self.tab2)

        self.tab4 = ttk.Frame(self.notebook)
        self.notebook.add(self.tab4, text="Log Analyzer")
        self.setup_tab4(self.tab4)

        self.refresh_ports()

    def setup_tab1(self, parent):
        main_pane = tk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_pane)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, minsize=600)
        main_pane.add(right_frame, minsize=300)

        conn_frame = ttk.LabelFrame(left_frame, text="Connection Settings")
        conn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(conn_frame, text="Port:").pack(side=tk.LEFT)
        self.port_combo = ttk.Combobox(conn_frame, width=10)
        self.port_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(conn_frame, text="Baud:").pack(side=tk.LEFT)
        self.baud_combo = ttk.Combobox(conn_frame, width=8, values=["9600", "115200", "57600"])
        self.baud_combo.current(1)
        self.baud_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(conn_frame, text="Line End:").pack(side=tk.LEFT)
        self.line_end_combo = ttk.Combobox(conn_frame, width=8, values=["\\r\\n", "\\n", "\\r"])
        self.line_end_combo.current(1)
        self.line_end_combo.pack(side=tk.LEFT, padx=5)

        self.btn_connect = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.btn_connect.pack(side=tk.LEFT, padx=10)

        self.btn_refresh = ttk.Button(conn_frame, text="Refresh Ports", command=self.refresh_ports)
        self.btn_refresh.pack(side=tk.LEFT)

        cmd_frame = ttk.LabelFrame(left_frame, text="Commands")
        cmd_frame.pack(fill=tk.X, padx=5, pady=5)

        r1 = ttk.Frame(cmd_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Button(r1, text="System Init", command=lambda: self.send_command("system init")).pack(side=tk.LEFT, padx=5)
        ttk.Button(r1, text="Get Time", command=lambda: self.send_command("get time")).pack(side=tk.LEFT, padx=5)
        ttk.Button(r1, text="Get Status", command=lambda: self.send_command("get status")).pack(side=tk.LEFT, padx=5)
        ttk.Button(r1, text="Help", command=lambda: self.send_command("help")).pack(side=tk.LEFT, padx=5)

        r2 = ttk.Frame(cmd_frame)
        r2.pack(fill=tk.X, pady=2)
        ttk.Button(r2, text="Set Time", command=self.cmd_set_time).pack(side=tk.LEFT, padx=5)
        self.entry_time = ttk.Entry(r2, width=10)
        self.entry_time.insert(0, "12:00")
        self.entry_time.pack(side=tk.LEFT, padx=5)
        ttk.Label(r2, text="(HH:MM)").pack(side=tk.LEFT)

        r4 = ttk.Frame(cmd_frame)
        r4.pack(fill=tk.X, pady=2)
        ttk.Label(r4, text="DAC (mV):").pack(side=tk.LEFT, padx=5)
        self.entry_dac = ttk.Entry(r4, width=8)
        self.entry_dac.insert(0, "1500")
        self.entry_dac.pack(side=tk.LEFT)
        ttk.Button(r4, text="Set DAC", command=self.cmd_set_dac).pack(side=tk.LEFT, padx=5)

        sensor_frame = ttk.LabelFrame(left_frame, text="Simulated Analog Sensors")
        sensor_frame.pack(fill=tk.X, padx=5, pady=5)
        self.sensor_widgets = {}
        self._build_sensor_panel(sensor_frame, 1, "Sensor 1 — DAC1 / PA4")
        self._build_sensor_panel(sensor_frame, 2, "Sensor 2 — DAC2 / PA5")

        term_frame = ttk.LabelFrame(left_frame, text="Terminal Output")
        term_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.text_area = scrolledtext.ScrolledText(term_frame, state='disabled', height=15, bg="white", fg="black", font=("Consolas", 10))
        self.text_area.pack(fill=tk.BOTH, expand=True)
        ttk.Button(term_frame, text="Clear Output", command=lambda: self.clear_terminal(self.text_area)).pack(anchor=tk.E, pady=2)

        pin_frame = ttk.LabelFrame(right_frame, text="Pinout Mapping")
        pin_frame.pack(fill=tk.X, padx=5, pady=5)
        columns = ("Function", "Pin", "Description")
        self.tree = ttk.Treeview(pin_frame, columns=columns, show="headings", height=10)
        self.tree.heading("Function", text="Function")
        self.tree.heading("Pin", text="Pin")
        self.tree.heading("Description", text="Description")
        self.tree.column("Function", width=80)
        self.tree.column("Pin", width=60)
        self.tree.column("Description", width=120)
        pin_scroll = ttk.Scrollbar(pin_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=pin_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pin_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        pinout_data = [
            ("Valve 1", "PB0", "Input (Button B1)"),
            ("Valve 2", "PB1", "Input"),
            ("Valve 3", "PB2", "Input"),
            ("Valve 4", "PB10", "Input"),
            ("Valve 5", "PB11", "Input"),
            ("Valve 6", "PB12", "Input"),
            ("Valve 7", "PB13", "Input"),
            ("Valve 8", "PB14", "Input"),
            ("Valve 9", "PB15", "Input"),
            ("Valve 10", "PC6", "Input"),
            ("Valve 11", "PC7", "Input"),
            ("Valve 12", "PC8", "Input"),
            ("Valve 13", "PC9", "Input"),
            ("Valve 14", "PA8", "Input"),
            ("Valve 15", "PA9", "Input"),
            ("Valve 16", "PA10", "Input"),
            ("", "", ""),
            ("WM 1", "PC0", "Output (Pulse)"),
            ("WM 2", "PC1", "Output (Pulse)"),
            ("WM 3", "PC2", "Output (Pulse)"),
            ("WM 4", "PC3", "Output (Pulse)"),
            ("WM 5", "PC4", "Output (Pulse)"),
            ("", "", ""),
            ("PS 1", "PA15", "Output (ON/OFF)"),
            ("PS 2", "PC10", "Output (ON/OFF)"),
            ("PS 3", "PC11", "Output (ON/OFF)"),
            ("PS 4", "PC12", "Output (ON/OFF)"),
            ("PS 5", "PD2", "Output (ON/OFF)"),
            ("", "", ""),
            ("DAC 1", "PA4", "Analog Output 0-3.3V"),
            ("DAC 2", "PA5", "Analog Output 0-3.3V"),
        ]
        for item in pinout_data:
            self.tree.insert("", tk.END, values=item)

        # WM Pulse Monitor graph
        graph_outer = ttk.LabelFrame(right_frame, text="WM Pulse Monitor")
        graph_outer.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        cb_frame = ttk.Frame(graph_outer)
        cb_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        # Header
        ttk.Label(cb_frame, text="Show",    font=('', 8, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(cb_frame, text="Cycle ms", font=('', 8, 'bold')).grid(row=0, column=1, sticky='w', padx=2)
        ttk.Label(cb_frame, text="Start",   font=('', 8, 'bold')).grid(row=0, column=2, sticky='w', padx=1)
        ttk.Label(cb_frame, text="Stop",    font=('', 8, 'bold')).grid(row=0, column=3, sticky='w', padx=1)
        ttk.Label(cb_frame, text="Trigger", font=('', 8, 'bold')).grid(row=0, column=4, sticky='w', padx=1)
        ttk.Label(cb_frame, text="On/Off",  font=('', 8, 'bold')).grid(row=0, column=5, sticky='w', padx=1)

        self.wm_show_vars = {}
        self.wm_rate_vars = {}
        for i in range(1, 6):
            show_var = tk.BooleanVar(value=True)
            self.wm_show_vars[i] = show_var
            rate_var = tk.StringVar(value="1000")
            self.wm_rate_vars[i] = rate_var
            rate_var.trace_add('write', lambda *_, wid=i: self._on_rate_change(wid))
            ttk.Checkbutton(cb_frame, text=f'WM {i}', variable=show_var,
                            command=self.update_wm_graph).grid(row=i, column=0, sticky='w', pady=2)
            ttk.Entry(cb_frame, textvariable=rate_var, width=5).grid(row=i, column=1, padx=2, pady=2)
            ttk.Button(cb_frame, text="▶", width=2,
                       command=lambda wid=i: self._cmd_wm_start(wid)
                       ).grid(row=i, column=2, padx=1)
            ttk.Button(cb_frame, text="■", width=2,
                       command=lambda wid=i: self._cmd_wm_stop(wid)
                       ).grid(row=i, column=3, padx=1)
            ttk.Button(cb_frame, text="T", width=2,
                       command=lambda wid=i: self._cmd_wm_trigger(wid)
                       ).grid(row=i, column=4, padx=1)
            # The new board has only WM1-WM4
            if i <= 4:
                ttk.Button(cb_frame, text="ON/OFF", width=7,
                           command=lambda wid=i: self._cmd_wm_toggle(wid)
                           ).grid(row=i, column=5, padx=1)

        ttk.Button(cb_frame, text="Reset Graph", command=self.reset_wm_graph).grid(
            row=6, column=0, columnspan=6, pady=8, sticky='ew')

        fig_frame = ttk.Frame(graph_outer)
        fig_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.wm_fig = Figure(figsize=(4, 3), dpi=80)
        self.wm_fig.set_tight_layout(True)
        self.wm_ax = self.wm_fig.add_subplot(111)
        self.wm_ax.set_ylabel('Pulses')
        self.wm_ax.set_xlabel('Time')
        self.wm_ax.set_title('WM Cumulative Pulses')
        self.wm_canvas = FigureCanvasTkAgg(self.wm_fig, master=fig_frame)
        self.wm_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def setup_tab2(self, parent):
        conn_frame = ttk.LabelFrame(parent, text="Secondary Connection Settings")
        conn_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(conn_frame, text="Port:").pack(side=tk.LEFT)
        self.port_combo_2 = ttk.Combobox(conn_frame, width=10)
        self.port_combo_2.pack(side=tk.LEFT, padx=5)

        ttk.Label(conn_frame, text="Baud:").pack(side=tk.LEFT)
        self.baud_combo_2 = ttk.Combobox(conn_frame, width=8, values=["9600", "115200", "57600"])
        self.baud_combo_2.current(1)
        self.baud_combo_2.pack(side=tk.LEFT, padx=5)

        ttk.Label(conn_frame, text="Line End:").pack(side=tk.LEFT)
        self.line_end_combo_2 = ttk.Combobox(conn_frame, width=8, values=["\\r\\n", "\\n", "\\r"])
        self.line_end_combo_2.current(1)
        self.line_end_combo_2.pack(side=tk.LEFT, padx=5)

        self.btn_connect_2 = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection_2)
        self.btn_connect_2.pack(side=tk.LEFT, padx=10)

        self.btn_refresh_2 = ttk.Button(conn_frame, text="Refresh Ports", command=self.refresh_ports)
        self.btn_refresh_2.pack(side=tk.LEFT)

        init_frame = ttk.LabelFrame(parent, text="System Initialization")
        init_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(init_frame, text="Run Config Settings", command=self.run_full_init).pack(side=tk.LEFT, padx=5)

        cmd_frame = ttk.LabelFrame(parent, text="Command Builder")
        cmd_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(cmd_frame, text="Category:").pack(side=tk.LEFT, padx=5)
        self.cmd_cat_combo = ttk.Combobox(cmd_frame, width=10, state="readonly")
        self.cmd_cat_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(cmd_frame, text="Action:").pack(side=tk.LEFT, padx=5)
        self.cmd_act_combo = ttk.Combobox(cmd_frame, width=10, state="readonly")
        self.cmd_act_combo.pack(side=tk.LEFT, padx=5)

        ttk.Label(cmd_frame, text="Args:").pack(side=tk.LEFT, padx=5)
        self.cmd_args_entry = ttk.Entry(cmd_frame, width=20)
        self.cmd_args_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(cmd_frame, text="Send", command=self.send_builder_command).pack(side=tk.LEFT, padx=10)

        self.cli_commands = {
            "Tab": [], "?": [], "Device": ["Info", "Reset"], "Flash": ["Test", "SwitchBank"],
            "RTC": ["Time", "Date"], "OS": ["Info"], "ADC": ["Get", "Test", "Enable"],
            "CRC": ["Calc32", "Calc16"], "AI": ["Info", "Config", "Enable", "Read", "Reset"],
            "AS": ["dump"], "PR": ["set", "setbits", "get"],
            "DI": ["Info", "Config", "Enable", "Feed", "PinIrq", "Reset", "Count", "Get", "PinGet", "RstCnt", "Test"],
            "wm": ["status", "debug"], "DO": ["Info", "Config", "Enable", "Open", "Close", "Reset"],
            "DFM": ["Enable"], "BLE": ["Info", "Enable", "SendMsg", "GetMsg", "SendMacCmd", "GetMac"],
            "SDI": ["Info", "Config", "SendCmd", "GetData", "Reset"], "Temp": ["Init", "Read"],
            "GPIO": ["Enable", "Get"], "RSW": ["Get"],
            "Cell": ["Info", "Enable", "SendMsg", "Get", "SendHex"],
            "SDCARD": ["Info", "Enable", "Mount", "UnMount", "Format", "CreateDir", "CreateFile",
                       "DeleteFile", "UpdateFile", "ReadFile", "CloseFile", "RenameFile", "ReadString",
                       "CheckSpace", "Scan", "PrintFile", "GetFileSize"],
            "FOTA": ["SdCard", "BleTx", "Test"], "RS485": ["Info", "Enable", "SendMsg", "SendHexMsg", "GetMsg"],
            "FlashOB": ["Set"], "IrrProg": ["Info", "Config", "Reset", "FlashSave"],
            "Shift": ["Info", "Config", "Reset"], "Recipe": ["Info", "Config", "Reset", "FlashSave"],
            "IrrGen": ["Info", "Config", "Reset", "FlashSave"], "IrrAlarm": ["Info", "Config", "Reset", "FlashSave"],
            "IrrDOMap": ["Info", "Config", "Reset", "FlashSave"], "IrrDIMap": ["Info", "Config", "Reset", "FlashSave"],
            "IrrAIMap": ["Info", "Config", "Reset", "FlashSave"],
            "IrrQueue": ["Test", "Print", "Clear", "FlashGet", "FlashSave", "FlashReset"],
            "IrrDO": ["Open", "Close"], "IrrRep": ["Print"], "IrrCmd": ["Set", "Get"],
            "Uncomplt": ["FlashGet", "FlashSave", "FlashErase"],
            "IrrMngr": ["FlashGet", "FlashSave", "FlashReset"], "MQUncmp": ["FlashSave"],
            "Log": ["Write", "Read", "ReadArr", "GetSize", "Print", "Erase", "Test"],
            "KA": ["Send", "Irr", "Alert", "Scheme", "Recipes", "Settings", "IOConfig"]
        }

        self.cmd_cat_combo['values'] = list(self.cli_commands.keys())
        self.cmd_cat_combo.bind("<<ComboboxSelected>>", self.update_action_combo)
        if self.cli_commands:
            self.cmd_cat_combo.current(0)
            self.update_action_combo(None)

        send_frame = ttk.LabelFrame(parent, text="Send Data")
        send_frame.pack(fill=tk.X, padx=10, pady=5)
        self.entry_send_2 = ttk.Entry(send_frame)
        self.entry_send_2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.entry_send_2.bind("<Return>", lambda event: self.send_command_2())
        ttk.Button(send_frame, text="Send", command=self.send_command_2).pack(side=tk.LEFT, padx=5)

        term_frame = ttk.LabelFrame(parent, text="Terminal Output")
        term_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.text_area_2 = scrolledtext.ScrolledText(term_frame, state='disabled', height=15, bg="white", fg="black", font=("Consolas", 10))
        self.text_area_2.pack(fill=tk.BOTH, expand=True)
        ttk.Button(term_frame, text="Clear Output", command=lambda: self.clear_terminal(self.text_area_2)).pack(anchor=tk.E, pady=2)

    def _on_rate_change(self, wm_id):
        """Called on every keystroke in the rate entry; debounced 500 ms."""
        pending = self._rate_debounce_ids.get(wm_id)
        if pending:
            self.root.after_cancel(pending)
        self._rate_debounce_ids[wm_id] = self.root.after(500, self._apply_rate_change, wm_id)

    def _apply_rate_change(self, wm_id):
        """Apply a new cycle-time while the WM is running (no Play needed)."""
        self._rate_debounce_ids[wm_id] = None
        if not self.wm_active[wm_id]:
            return   # not running — nothing to do
        rate, error = self._parse_positive_rate(self.wm_rate_vars[wm_id].get())
        if error:
            return   # silently ignore while typing — no popup spam on every keystroke
        # Send updated cycle time to firmware
        self.send_command(f"start wm {wm_id} {int(rate)}")
        # Cancel the pending GUI toggle and reschedule immediately with new rate
        if self.wm_after_ids[wm_id] is not None:
            self.root.after_cancel(self.wm_after_ids[wm_id])
            self.wm_after_ids[wm_id] = None
        self._schedule_pulse_toggle(wm_id)

    @staticmethod
    def _parse_positive_rate(text):
        """Parse a rate string. Returns (value, error) — error is None on success."""
        try:
            value = float(text)
        except (TypeError, ValueError):
            return None, "Rate must be a number"
        if value <= 0:
            return None, "Rate must be greater than 0"
        return value, None

    def _cmd_wm_start(self, wm_id):
        rate, error = self._parse_positive_rate(self.wm_rate_vars[wm_id].get())
        if error:
            messagebox.showwarning("Invalid Rate", f"WM{wm_id}: {error}")
            return
        self.send_command(f"start wm {wm_id} {int(rate)}")
        self.start_wm_pulse(wm_id)

    def _cmd_wm_stop(self, wm_id):
        self.send_command(f"stop wm {wm_id}")
        self.stop_wm_pulse(wm_id)

    def _cmd_wm_trigger(self, wm_id):
        rate, error = self._parse_positive_rate(self.wm_rate_vars[wm_id].get())
        if error:
            messagebox.showwarning("Invalid Rate", f"WM{wm_id}: {error}")
            return
        self.send_command(f"trigger wm {wm_id} {int(rate)}")

    def _cmd_wm_toggle(self, wm_id):
        self.send_command(f"toggle wm {wm_id}")

    def start_wm_pulse(self, wm_id):
        if not (1 <= wm_id <= 5) or self.wm_active[wm_id]:
            return
        self.wm_active[wm_id] = True
        self._schedule_pulse_toggle(wm_id)
        self._ensure_graph_refresh()

    def stop_wm_pulse(self, wm_id):
        if not (1 <= wm_id <= 5):
            return
        self.wm_active[wm_id] = False
        if self.wm_after_ids[wm_id] is not None:
            self.root.after_cancel(self.wm_after_ids[wm_id])
            self.wm_after_ids[wm_id] = None
        self.wm_pulse_state[wm_id] = 0
        now = datetime.now()
        self.wm_pulse_data[wm_id].append((now, 0))
        self._wm_csv_write_row(now, wm_id, 0)
        self.update_wm_graph()

    def _schedule_pulse_toggle(self, wm_id):
        if not self.wm_active[wm_id]:
            return
        try:
            rate = float(self.wm_rate_vars[wm_id].get())
            if rate <= 0:
                rate = 1000.0
        except (ValueError, AttributeError):
            rate = 1000.0
        half_period_ms = max(50, int(rate / 2))
        self.wm_pulse_state[wm_id] ^= 1
        now = datetime.now()
        self.wm_pulse_data[wm_id].append((now, self.wm_pulse_state[wm_id]))
        self._wm_csv_write_row(now, wm_id, self.wm_pulse_state[wm_id])
        # Keep only last 2 minutes of data (graph display only)
        cutoff = now - timedelta(seconds=120)
        self.wm_pulse_data[wm_id] = [(t, v) for t, v in self.wm_pulse_data[wm_id] if t >= cutoff]
        self.wm_after_ids[wm_id] = self.root.after(half_period_ms, self._schedule_pulse_toggle, wm_id)

    def _ensure_graph_refresh(self):
        if self._graph_refresh_id is None:
            self._graph_refresh()

    def _graph_refresh(self):
        self._graph_refresh_id = None
        self.update_wm_graph()
        if any(self.wm_active.values()):
            self._all_stopped_time = None
            self._graph_refresh_id = self.root.after(400, self._graph_refresh)
        else:
            if self._all_stopped_time is None:
                self._all_stopped_time = datetime.now()
            elapsed = (datetime.now() - self._all_stopped_time).total_seconds()
            if elapsed < 10:
                self._graph_refresh_id = self.root.after(400, self._graph_refresh)

    def reset_wm_graph(self):
        for i in range(1, 6):
            self.wm_active[i] = False
            if self.wm_after_ids[i] is not None:
                self.root.after_cancel(self.wm_after_ids[i])
                self.wm_after_ids[i] = None
        if self._graph_refresh_id is not None:
            self.root.after_cancel(self._graph_refresh_id)
            self._graph_refresh_id = None
        self.wm_pulse_data = {i: [] for i in range(1, 6)}
        self.wm_pulse_state = {i: 0 for i in range(1, 6)}
        self._wm_csv_close()
        self.update_wm_graph()

    # -------------------------------------------------------------------------
    # Auto-CSV helpers
    # -------------------------------------------------------------------------

    def _wm_csv_open(self):
        """Open (or re-open after midnight) the auto-save CSV file."""
        import csv as _csv
        self._wm_csv_close()
        today = datetime.now().date()
        date_str = today.strftime('%Y-%m-%d')
        fname = f"wm_pulses_{date_str}.csv"
        logs_dir = getattr(self, '_logs_dir', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'FLEX_LOGS'))
        os.makedirs(logs_dir, exist_ok=True)
        path = os.path.join(logs_dir, fname)
        try:
            self._wm_csv_file   = open(path, 'a', newline='', encoding='utf-8')
            self._wm_csv_writer = _csv.writer(self._wm_csv_file)
            self._wm_csv_date   = today
            self._wm_csv_path   = path
            self._wm_csv_write_errors = 0   # reset error counter
            # Write header only when file is new / empty
            if self._wm_csv_file.tell() == 0:
                self._wm_csv_writer.writerow(['Time', 'WM1', 'WM2', 'WM3', 'WM4', 'WM5'])
                self._wm_csv_file.flush()
        except Exception as e:
            self._wm_csv_file = self._wm_csv_writer = None
            messagebox.showwarning("WM CSV Error",
                f"Cannot create CSV file:\n{path}\n\nReason: {e}\n\nPulse data will NOT be saved.")
            print(f"[WM CSV] Cannot open {path}: {e}")

    def _wm_csv_close(self):
        """Flush and close the auto-save CSV file if open."""
        if self._wm_csv_file:
            try:
                self._wm_csv_file.flush()
                self._wm_csv_file.close()
            except Exception:
                pass
        self._wm_csv_file   = None
        self._wm_csv_writer = None

    def _wm_csv_write_row(self, t, changed_wm_id, new_state):
        """Write one row: timestamp + current state of all 5 WMs.
        Also handles midnight rollover – closes current file and opens a new one."""
        # Midnight rollover check
        if self._wm_csv_date and t.date() != self._wm_csv_date:
            self._wm_csv_close()

        # Lazy open: create file on first write
        if self._wm_csv_writer is None:
            self._wm_csv_open()
        if self._wm_csv_writer is None:
            return

        # Write TWO rows at the same timestamp to create a perfect vertical edge in Excel:
        # Row 1 = state BEFORE the transition (old value for changed_wm_id)
        # Row 2 = state AFTER  the transition (new value for changed_wm_id)
        # Excel Scatter-with-Lines connects same-time points vertically → square wave.
        t_str = t.strftime('%H:%M:%S.%f')[:-3]   # HH:MM:SS.mmm
        try:
            # Row 1: old state (changed WM had the opposite value)
            old_states = [self.wm_pulse_state[i] if i != changed_wm_id else (1 - new_state)
                          for i in range(1, 6)]
            self._wm_csv_writer.writerow([t_str] + old_states)
            # Row 2: new state (as updated by caller)
            new_states = [self.wm_pulse_state[i] for i in range(1, 6)]
            self._wm_csv_writer.writerow([t_str] + new_states)
            self._wm_csv_file.flush()
            self._wm_csv_write_errors = 0   # reset on success
        except Exception as e:
            self._wm_csv_write_errors = getattr(self, '_wm_csv_write_errors', 0) + 1
            print(f"[WM CSV] Write error: {e}")
            # Show warning only on first failure (avoid spam)
            if self._wm_csv_write_errors == 1:
                messagebox.showwarning("WM CSV Write Error",
                    f"Cannot write to CSV file.\n\n"
                    f"Reason: {e}\n\n"
                    f"Is the file open in Excel?\n"
                    f"Close it in Excel and click Reset Graph to restart recording.")
            # After 5 consecutive failures, close and stop trying
            if self._wm_csv_write_errors >= 5:
                print("[WM CSV] Too many errors – stopping CSV recording.")
                self._wm_csv_close()

    def update_wm_graph(self):
        if not hasattr(self, 'wm_ax'):
            return
        self.wm_ax.clear()
        self.wm_ax.set_xlabel('Time')
        self.wm_ax.set_title('WM Pulse Signal (Real-time)')
        ytick_pos = []
        ytick_lbl = []
        has_data = False
        for wm_id in range(1, 6):
            offset = self.wm_offsets[wm_id]
            ytick_pos.append(offset + 0.5)
            ytick_lbl.append(f'WM {wm_id}')
            if not hasattr(self, 'wm_show_vars') or not self.wm_show_vars[wm_id].get():
                continue
            self.wm_ax.axhline(y=offset, color=self.wm_colors[wm_id],
                               linewidth=0.5, linestyle='--', alpha=0.4)
            data = self.wm_pulse_data[wm_id]
            if data:
                times = [t for t, v in data]
                vals = [v + offset for t, v in data]
                self.wm_ax.step(times, vals, where='post',
                                color=self.wm_colors[wm_id], linewidth=1.5)
                has_data = True
        self.wm_ax.set_yticks(ytick_pos)
        self.wm_ax.set_yticklabels(ytick_lbl, fontsize=8)
        self.wm_ax.set_ylim(-0.2, 7.2)
        if has_data or not all(
            len(self.wm_pulse_data[i]) == 0 for i in range(1, 6)
        ):
            now = datetime.now()
            x_start = now - timedelta(seconds=120)
            x_end = now + timedelta(seconds=10)
            self.wm_ax.set_xlim(
                mdates.date2num(x_start),
                mdates.date2num(x_end)
            )
            self.wm_ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.wm_fig.autofmt_xdate()
        self.wm_canvas.draw_idle()

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        self.port_combo['values'] = port_list
        self.port_combo_2['values'] = port_list
        if ports:
            if not self.port_combo.get():
                self.port_combo.current(0)
            if not self.port_combo_2.get():
                self.port_combo_2.current(0)

    def toggle_connection(self):
        if not self.is_connected:
            try:
                port = self.port_combo.get()
                if self.is_connected_2 and self.serial_port_2 and self.serial_port_2.port == port:
                    messagebox.showerror("Connection Error", f"{port} is already in use by FLEX CLI.")
                    return
                baud = int(self.baud_combo.get())
                self.serial_port = serial.Serial(port, baud, timeout=1, dsrdtr=False, rtscts=False)
                self.serial_port.dtr = False
                self.serial_port.rts = False
                self.is_connected = True
                self.btn_connect.config(text="Disconnect")
                self.stop_read = False
                self.read_thread = threading.Thread(target=self.read_serial)
                self.read_thread.daemon = True
                self.read_thread.start()
                self.log(self.text_area, "Connected to " + port)
            except Exception as e:
                messagebox.showerror("Connection Error", str(e))
        else:
            self.stop_read = True
            if self.serial_port:
                self.serial_port.close()
            self.is_connected = False
            self.btn_connect.config(text="Connect")
            self.log(self.text_area, "Disconnected")

    def read_serial(self):
        while not self.stop_read and self.serial_port and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    try:
                        self.buffer_1 += data.decode('utf-8', errors='ignore')
                        while '\n' in self.buffer_1:
                            line, self.buffer_1 = self.buffer_1.split('\n', 1)
                            line = line.rstrip('\r')
                            if line:
                                valve_open  = re.search(r'valve (\d+) open',  line)
                                valve_close = re.search(r'valve (\d+) close', line)
                                wm_started  = re.search(r'wm (\d+) started working', line)
                                wm_stopped  = re.search(r'wm (\d+) stopped working', line)
                                if valve_open:
                                    wm_id = int(valve_open.group(1))
                                    if 1 <= wm_id <= 5:
                                        self.root.after(0, self.start_wm_pulse, wm_id)
                                elif valve_close:
                                    wm_id = int(valve_close.group(1))
                                    if 1 <= wm_id <= 5:
                                        self.root.after(0, self.stop_wm_pulse, wm_id)
                                elif wm_started:
                                    wm_id = int(wm_started.group(1))
                                    if 1 <= wm_id <= 5:
                                        self.root.after(0, self.start_wm_pulse, wm_id)
                                elif wm_stopped:
                                    wm_id = int(wm_stopped.group(1))
                                    if 1 <= wm_id <= 5:
                                        self.root.after(0, self.stop_wm_pulse, wm_id)
                                self.root.after(0, self.log, self.text_area, line, True)
                    except:
                        pass
                time.sleep(0.01)
            except Exception as e:
                self.root.after(0, self.log, self.text_area, f"\nError reading: {e}\n")
                break

    def send_command(self, cmd):
        if not self.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to a COM port first.")
            return
        line_end_map = {"\\r\\n": "\r\n", "\\n": "\n", "\\r": "\r"}
        line_end = line_end_map.get(self.line_end_combo.get(), "\n")
        full_cmd = cmd + line_end
        try:
            self.serial_port.write(full_cmd.encode('utf-8'))
            self.log(self.text_area, f"> {cmd}\n")
        except Exception as e:
            self.log(self.text_area, f"Error sending: {e}\n")

    def toggle_connection_2(self):
        if not self.is_connected_2:
            try:
                port = self.port_combo_2.get()
                if self.is_connected and self.serial_port and self.serial_port.port == port:
                    messagebox.showerror("Connection Error", f"{port} is already in use by Main Controller.")
                    return
                baud = int(self.baud_combo_2.get())
                self.serial_port_2 = serial.Serial(port, baud, timeout=1, dsrdtr=False, rtscts=False)
                self.serial_port_2.dtr = False
                self.serial_port_2.rts = False
                self.is_connected_2 = True
                self.btn_connect_2.config(text="Disconnect")
                self.stop_read_2 = False
                self.read_thread_2 = threading.Thread(target=self.read_serial_2)
                self.read_thread_2.daemon = True
                self.read_thread_2.start()
                cli_ts = time.strftime("%Y-%m-%d_%H-%M-%S")
                self.cli_log_file_path = os.path.join(
                    self._logs_dir, f"FLEX CLI LOGS {cli_ts}.txt"
                )
                try:
                    with open(self.cli_log_file_path, "w") as f:
                        f.write(f"--- FLEX CLI Log Started: {time.ctime()} ---\n")
                        f.write(f"--- Port: {port} | Baud: {baud} ---\n")
                except Exception as _e:
                    print(f"Error creating CLI log file: {_e}")
                    self.cli_log_file_path = None
                self.log(self.text_area_2, "Connected to " + port)
            except Exception as e:
                messagebox.showerror("Connection Error", str(e))
        else:
            self.stop_read_2 = True
            if self.serial_port_2:
                self.serial_port_2.close()
            self.is_connected_2 = False
            self.btn_connect_2.config(text="Connect")
            self.log(self.text_area_2, "Disconnected")

    def read_serial_2(self):
        while not self.stop_read_2 and self.serial_port_2 and self.serial_port_2.is_open:
            try:
                if self.serial_port_2.in_waiting > 0:
                    data = self.serial_port_2.read(self.serial_port_2.in_waiting)
                    try:
                        self.buffer_2 += data.decode('utf-8', errors='ignore')
                        while '\n' in self.buffer_2:
                            line, self.buffer_2 = self.buffer_2.split('\n', 1)
                            line = line.rstrip('\r')
                            if line:
                                self.root.after(0, self.log, self.text_area_2, line, True)
                                self.init_response_event.set()
                    except:
                        pass
                time.sleep(0.01)
            except Exception as e:
                self.root.after(0, self.log, self.text_area_2, f"\nError reading: {e}\n")
                break

    def send_command_2(self):
        cmd = self.entry_send_2.get()
        self._send_to_port_2(cmd)
        self.entry_send_2.delete(0, tk.END)

    def _send_to_port_2(self, cmd: str, force_crlf=False):
        if not self.is_connected_2:
            messagebox.showwarning("Not Connected", "Please connect to a COM port first.")
            return
        if force_crlf:
            line_end = "\n"
        else:
            line_end_map = {"\\r\\n": "\r\n", "\\n": "\n", "\\r": "\r"}
            line_end = line_end_map.get(self.line_end_combo_2.get(), "\n")
        full_cmd = cmd + line_end
        try:
            self.serial_port_2.write(full_cmd.encode())
            self.log(self.text_area_2, f"> {cmd}\n")
        except Exception as e:
            self.log(self.text_area_2, f"Error sending: {e}\n")

    def update_action_combo(self, event):
        cat = self.cmd_cat_combo.get()
        actions = self.cli_commands.get(cat, [])
        self.cmd_act_combo['values'] = actions
        if actions:
            self.cmd_act_combo.current(0)
        else:
            self.cmd_act_combo.set('')

    def send_builder_command(self):
        cat = self.cmd_cat_combo.get()
        act = self.cmd_act_combo.get()
        args = self.cmd_args_entry.get()
        cmd = f"{cat} {act}"
        if args:
            cmd += f" {args}"
        self._send_to_port_2(cmd)

    def run_full_init(self):
        threading.Thread(target=self._run_init_sequence, daemon=True).start()

    def _run_init_sequence(self):
        commands = [
            "do reset", "di reset", "ai reset", "do config", "di config",
            "di pinirq 0 1 1", "irrdomap reset", "irrdomap config", "irrdomap flashsave",
            "irrdimap reset", "irrdimap config", "irrdimap flashsave"
        ]
        for cmd in commands:
            self.root.after(0, self._send_to_port_2, cmd, True)
            time.sleep(0.5)

    def cmd_set_time(self):
        t = self.entry_time.get()
        self.send_command(f"set time {t}")

    def cmd_start_wm(self):
        wm_id = self.entry_wm_id.get()
        rate = self.entry_wm_rate.get()
        self.send_command(f"start wm {wm_id} {rate}")

    def cmd_stop_wm(self):
        wm_id = self.entry_wm_id.get()
        self.send_command(f"stop wm {wm_id}")

    def cmd_trigger_wm(self):
        wm_id = self.entry_wm_id.get()
        rate = self.entry_wm_rate.get()
        self.send_command(f"trigger wm {wm_id} {rate}")

    def cmd_set_dac(self):
        mv = self.entry_dac.get()
        self.send_command(f"set dac {mv}")

    def _build_sensor_panel(self, parent, sensor_id, title):
        """Build one 'simulated analog sensor' calibration panel (X1/X2/Y1/Y2/Desired -> Voltage -> Apply)."""
        panel = ttk.LabelFrame(parent, text=title)
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        fields = {}
        defaults = {"x1": "0.0", "x2": "3.3", "y1": "0", "y2": "10", "desired": "0"}
        labels = {"x1": "X1 (min V):", "x2": "X2 (max V):", "y1": "Y1 (value at X1):",
                  "y2": "Y2 (value at X2):", "desired": "Desired value:"}

        for row, key in enumerate(("x1", "x2", "y1", "y2", "desired")):
            ttk.Label(panel, text=labels[key]).grid(row=row, column=0, sticky="w", padx=5, pady=2)
            var = tk.StringVar(value=defaults[key])
            entry = ttk.Entry(panel, textvariable=var, width=10)
            entry.grid(row=row, column=1, sticky="w", padx=5, pady=2)
            var.trace_add("write", lambda *_, sid=sensor_id: self._on_sensor_field_change(sid))
            fields[key] = var

        ttk.Label(panel, text="Calculated Voltage:").grid(row=5, column=0, sticky="w", padx=5, pady=(8, 2))
        voltage_label = ttk.Label(panel, text="0.000 V")
        voltage_label.grid(row=5, column=1, sticky="w", padx=5, pady=(8, 2))

        ttk.Button(panel, text=f"Apply Sensor {sensor_id}",
                   command=lambda sid=sensor_id: self._apply_sensor(sid)).grid(
            row=6, column=0, columnspan=2, pady=8, sticky="ew")

        self.sensor_widgets[sensor_id] = {"fields": fields, "voltage_label": voltage_label, "voltage": None}
        self._on_sensor_field_change(sensor_id)

    def _calc_sensor_voltage(self, sensor_id):
        """Parse+validate a sensor's fields and return (voltage, error_message).

        On success: (clamped_voltage_float, None).
        On failure: (None, "short error string").
        """
        fields = self.sensor_widgets[sensor_id]["fields"]
        try:
            x1 = float(fields["x1"].get())
            x2 = float(fields["x2"].get())
            y1 = float(fields["y1"].get())
            y2 = float(fields["y2"].get())
            desired = float(fields["desired"].get())
        except ValueError:
            return None, "Invalid input"

        if x2 == x1 or y2 == y1:
            return None, "X2/Y2 must differ from X1/Y1"

        voltage = x1 + (desired - y1) * (x2 - x1) / (y2 - y1)
        voltage = max(0.0, min(3.3, voltage))
        return voltage, None

    def _on_sensor_field_change(self, sensor_id):
        """Live recompute of the Calculated Voltage label as the user edits any field (no serial traffic)."""
        widgets = self.sensor_widgets[sensor_id]
        voltage, error = self._calc_sensor_voltage(sensor_id)
        if error:
            widgets["voltage"] = None
            widgets["voltage_label"].config(text=error)
        else:
            widgets["voltage"] = voltage
            widgets["voltage_label"].config(text=f"{voltage:.3f} V")

    def _apply_sensor(self, sensor_id):
        """Send the currently calculated voltage for one sensor as set dac1/set dac2 <mV>."""
        voltage, error = self._calc_sensor_voltage(sensor_id)
        if error:
            messagebox.showwarning("Invalid Sensor Calibration", error)
            return
        mv = round(voltage * 1000)
        self.send_command(f"set dac{sensor_id} {mv}")

    def cmd_set_mode(self):
        # index 0 → mode 1, index 1 → mode 2
        mode = self.mode_combo.current() + 1
        self.send_command(f"set mode {mode}")

    def log(self, text_widget, text, newline=True):
        text = re.sub(r'^\d+:\d+:\d+ - ', '', text)

        try:
            now = datetime.now()
            if hasattr(self, 'current_log_day') and now.day != self.current_log_day:
                self.current_log_day = now.day
                date_msg = f"--- Date Changed: {now.ctime()} ---"
                text_widget.config(state='normal')
                text_widget.insert(tk.END, f"{date_msg}\n")
                if text_widget == self.text_area:
                    try:
                        with open(self.log_file_path, "a") as f:
                            f.write(f"\n{date_msg}\n")
                    except:
                        pass
        except Exception as e:
            print(f"Error in date check: {e}")

        timestamp = time.strftime("[%H:%M:%S] ")
        if text.strip():
            final_text = f"{timestamp}{text}"
        else:
            final_text = text

        text_widget.config(state='normal')
        text_widget.insert(tk.END, final_text + ("\n" if newline else ""))

        if float(text_widget.index('end')) > 1000:
            text_widget.delete('1.0', '50.0')

        text_widget.see(tk.END)
        text_widget.config(state='disabled')

        if text_widget == self.text_area:
            try:
                with open(self.log_file_path, "a") as f:
                    f.write(final_text + ("\n" if newline else ""))
            except Exception:
                pass

        if text_widget == self.text_area_2 and self.cli_log_file_path:
            try:
                with open(self.cli_log_file_path, "a") as f:
                    f.write(final_text + ("\n" if newline else ""))
            except Exception:
                pass

    def setup_tab4(self, parent):
        ctrl_frame = ttk.LabelFrame(parent, text="Controls")
        ctrl_frame.pack(fill=tk.X, padx=10, pady=10)

        r1 = ttk.Frame(ctrl_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Button(r1, text="Load Log File", command=self.load_external_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(r1, text="Load Config (JSON)", command=self.load_config_file).pack(side=tk.LEFT, padx=5)
        self.lbl_config = ttk.Label(r1, text="No Config Loaded")
        self.lbl_config.pack(side=tk.LEFT, padx=5)

        r2 = ttk.Frame(ctrl_frame)
        r2.pack(fill=tk.X, pady=5)
        ttk.Button(r2, text="Run Test Scenario", command=self.run_scenario_test).pack(side=tk.LEFT, padx=5)

        res_frame = ttk.LabelFrame(parent, text="Analysis Results")
        res_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.analysis_text = scrolledtext.ScrolledText(res_frame, state='disabled', height=20, bg="#f0f0f0", font=("Consolas", 10))
        self.analysis_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.loaded_log_content = ""
        self.config_file_path = "test_config.json"
        if os.path.exists(self.config_file_path):
            self.lbl_config.config(text=f"Loaded: {os.path.basename(self.config_file_path)}")

    def load_config_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if file_path:
            self.config_file_path = file_path
            self.lbl_config.config(text=f"Loaded: {os.path.basename(file_path)}")

    def load_external_log(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    self.loaded_log_content = f.read()
                messagebox.showinfo("Success", f"Loaded {len(self.loaded_log_content)} bytes.")
                self.analysis_text.config(state='normal')
                self.analysis_text.delete(1.0, tk.END)
                self.analysis_text.insert(tk.END, f"Loaded log: {file_path}\n")
                self.analysis_text.config(state='disabled')
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")

    def run_scenario_test(self):
        if not self.loaded_log_content:
            messagebox.showwarning("Warning", "Please load a log file first.")
            return
        if not self.config_file_path:
            messagebox.showwarning("Warning", "Please load a JSON configuration file first.")
            return

        self.analysis_text.config(state='normal')
        self.analysis_text.delete(1.0, tk.END)
        self.analysis_text.insert(tk.END, f"--- Running Test Scenario --- {time.ctime()} ---\n")

        report_lines = []
        _ts_re = re.compile(r'\[(\d{2}:\d{2}:\d{2})\]')

        def gui_printer(msg):
            # Add timestamp prefix only on valve PASS/FAIL lines (not WM delta lines)
            stripped = msg.strip()
            is_pass_fail = stripped.startswith('[PASS]') or stripped.startswith('[FAIL]')
            is_wm_line   = 'WM' in stripped and 'delta' in stripped
            if is_pass_fail and not is_wm_line:
                ts_match = _ts_re.search(msg)
                ts = ts_match.group(1) if ts_match else datetime.now().strftime("%H:%M:%S")
                prefixed = f"[{ts}] {msg}"
            else:
                prefixed = msg
            self.analysis_text.insert(tk.END, prefixed + "\n")
            self.analysis_text.see(tk.END)
            report_lines.append(prefixed)

        try:
            engine = LogAnalyzerEngine(self.loaded_log_content, self.config_file_path, gui_printer)
            if engine.load_config():
                engine.parse_log()
                engine.run_test()
        except Exception as e:
            gui_printer(f"\nCRITICAL ERROR: {e}")

        self.analysis_text.config(state='disabled')

        # --- Save report to file ---
        try:
            log_dir = getattr(self, '_logs_dir', os.path.dirname(self.log_file_path) if hasattr(self, 'log_file_path') and self.log_file_path else os.getcwd())
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            report_path = os.path.join(log_dir, f"analysis_report_{timestamp}.txt")
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(f"--- Analysis Report --- {time.ctime()} ---\n")
                f.write(f"Log file:    {getattr(self, 'log_file_path', 'N/A')}\n")
                f.write(f"Config file: {self.config_file_path}\n")
                f.write("=" * 60 + "\n\n")
                for line in report_lines:
                    f.write(line + "\n")
            gui_printer(f"\n[REPORT] Saved to: {report_path}")
        except Exception as e:
            gui_printer(f"\n[REPORT] Failed to save report: {e}")

    def clear_terminal(self, text_widget):
        text_widget.config(state='normal')
        text_widget.delete(1.0, tk.END)
        text_widget.config(state='disabled')


if __name__ == "__main__":
    root = tk.Tk()
    app = FlexTesterGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app._wm_csv_close(), root.destroy()))
    root.mainloop()
