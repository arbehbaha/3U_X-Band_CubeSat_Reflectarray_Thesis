#!/usr/bin/env python3
"""
Anechoic chamber interactive test console (Rotor + VNA)

Rotor controller (Sunol Sciences SC104V):
  CH1 -> GPIB0::20::INSTR
  CH2 -> GPIB0::21::INSTR  (Azimuth)
  CH3 -> GPIB0::22::INSTR

Rotor command semantics (per user):
  - "CP <angle>"  : calibrate / set current position (DO NOT MOVE)
  - "CP"          : query current position (returns current angle)
  - "GOTO <angle>": move to absolute position in degrees

VNA (HP 8720C):
  Single-point S21 at a specified frequency using START=STOP, POIN 3, MARK1, OUTPMARK.

Interactive commands:
  help
  rotor <ch> <w|q> <command>
  vna [freq_ghz]
  ant      (antenna test mode: prompts for points/frequency/csv and runs sweep)
  status
  quit

Antenna test mode behavior:
  - Prompt for: number of points, CW frequency, CSV path
  - Calibrate CH2 to -180 deg via: "CP -180"  (no motion)
  - Move to -180 deg via: "GOTO -180.00"
  - For N points:
      - wait until rotor has settled at target by polling "CP"
      - measure S21 at requested frequency
      - append to CSV (includes angle_deg)
      - command next angle with "GOTO <angle>"
  - At end: return to start pos via "GOTO -180" and wait until settled
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

import pyvisa


# -----------------------------
# Config
# -----------------------------

@dataclass(frozen=True)
class RotorConfig:
    board: int = 0
    channel_to_addr: dict[int, int] = None
    timeout_ms: int = 6000
    write_termination: str = "\n"
    read_termination: str = "\n"


@dataclass(frozen=True)
class VNAConfig:
    resource: str = "GPIB0::16::INSTR"  # <-- change if needed
    timeout_ms: int = 10000
    write_termination: str = "\n"
    read_termination: str = "\n"


DEFAULT_ROTOR = RotorConfig(channel_to_addr={1: 20, 2: 21, 3: 22})
DEFAULT_VNA = VNAConfig()

AZ_CH = 2  # Azimuth channel


# Rotor settle tuning
POS_TOL_DEG = 1          # considered "at target" if within this many degrees
STABLE_COUNT_REQUIRED = 3   # require N consecutive readings within tolerance
POLL_INTERVAL_S = 0.25      # seconds between CP polls
MAX_WAIT_S = 120.0          # maximum wait per move before giving up


# -----------------------------
# Utility
# -----------------------------

def gpib_resource(board: int, primary_addr: int) -> str:
    return f"GPIB{board}::{primary_addr}::INSTR"


def safe_timeout_read(inst) -> Optional[str]:
    """Try to read one line; return None if timeout/no data."""
    try:
        return inst.read()
    except pyvisa.errors.VisaIOError as e:
        if e.error_code == pyvisa.constants.StatusCode.error_timeout:
            return None
        raise


def drain_reads(inst, max_reads: int = 5):
    """Clear any pending output without failing."""
    for _ in range(max_reads):
        s = safe_timeout_read(inst)
        if s is None:
            break


def prompt_int(prompt: str, min_value: int = 1) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            v = int(raw)
            if v < min_value:
                print(f"Value must be >= {min_value}.")
                continue
            return v
        except ValueError:
            print("Please enter an integer.")


def prompt_float(prompt: str, default: Optional[float] = None) -> float:
    while True:
        raw = input(prompt).strip()
        if raw == "" and default is not None:
            return float(default)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number.")


def fmt_angle(angle_deg: float) -> str:
    # Format like "100.00" per your example
    return f"{angle_deg:.2f}"


def parse_first_float(text: str) -> float:
    """
    Extract a float from a response string.
    Accepts things like: "100.00", "CP 100.00", "100.00 DEG", etc.
    """
    s = text.strip()
    # Keep only chars that can appear in a float token
    token_chars = set("0123456789+-.eE")
    tokens = []
    current = []
    for ch in s:
        if ch in token_chars:
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    if not tokens:
        raise ValueError(f"Could not parse position from: {text!r}")
    return float(tokens[0])


# -----------------------------
# Rotor Controller
# -----------------------------

class RotorController:
    def __init__(self, rm: pyvisa.ResourceManager, cfg: RotorConfig):
        self.rm = rm
        self.cfg = cfg
        self.sessions: dict[int, pyvisa.resources.MessageBasedResource] = {}

    def open(self):
        for ch, addr in self.cfg.channel_to_addr.items():
            res = gpib_resource(self.cfg.board, addr)
            inst = self.rm.open_resource(res)
            inst.timeout = self.cfg.timeout_ms
            inst.write_termination = self.cfg.write_termination
            inst.read_termination = self.cfg.read_termination
            self.sessions[ch] = inst

    def close(self):
        for inst in self.sessions.values():
            try:
                inst.close()
            except Exception:
                pass
        self.sessions.clear()

    def write(self, ch: int, cmd: str):
        self.sessions[ch].write(cmd)

    def query(self, ch: int, cmd: str) -> str:
        return self.sessions[ch].query(cmd)

    def try_read_all(self, ch: int, max_reads: int = 10, inter_delay_s: float = 0.03) -> str:
        inst = self.sessions[ch]
        chunks: list[str] = []
        for _ in range(max_reads):
            s = safe_timeout_read(inst)
            if s is None:
                break
            chunks.append(str(s))
            time.sleep(inter_delay_s)
        return "\n".join(chunks).strip()

    def get_position_deg(self, ch: int) -> float:
        """
        Uses rotor query 'CP' to read current position.
        """
        resp = self.query(ch, "CP")
        return parse_first_float(resp)

    def wait_until_settled(
        self,
        ch: int,
        target_deg: float,
        tol_deg: float = POS_TOL_DEG,
        stable_count_required: int = STABLE_COUNT_REQUIRED,
        poll_interval_s: float = POLL_INTERVAL_S,
        max_wait_s: float = MAX_WAIT_S,
    ) -> float:
        """
        Poll 'CP' until the reported position is within tol_deg of target_deg
        for stable_count_required consecutive polls.
        Returns the last measured position.

        Raises TimeoutError if not settled within max_wait_s.
        """
        stable = 0
        last_pos = None
        t0 = time.time()

        while True:
            if time.time() - t0 > max_wait_s:
                raise TimeoutError(
                    f"Rotor CH{ch} did not settle to {target_deg:.2f} deg "
                    f"within {max_wait_s:.1f} s (last={last_pos})"
                )

            try:
                pos = self.get_position_deg(ch)
                last_pos = pos
            except Exception:
                # If parsing/comm hiccup occurs, just treat as not-stable and retry
                stable = 0
                time.sleep(poll_interval_s)
                continue

            if abs(pos - target_deg) <= tol_deg:
                stable += 1
            else:
                stable = 0

            if stable >= stable_count_required:
                return pos

            time.sleep(poll_interval_s)


# -----------------------------
# VNA (HP 8720C single-point S21)
# -----------------------------

def parse_outpmark(resp: str) -> tuple[float, float, float]:
    parts = [p.strip() for p in resp.strip().split(",") if p.strip()]
    if len(parts) < 3:
        raise ValueError(f"Unexpected OUTPMARK response: {resp!r}")
    marker_val = float(parts[0])
    marker_aux = float(parts[1])
    stimulus = float(parts[2])
    return marker_val, marker_aux, stimulus


class HP8720C:
    def __init__(self, rm: pyvisa.ResourceManager, cfg: VNAConfig):
        self.rm = rm
        self.cfg = cfg
        self.inst: Optional[pyvisa.resources.MessageBasedResource] = None

    def open(self):
        self.inst = self.rm.open_resource(self.cfg.resource)
        self.inst.timeout = self.cfg.timeout_ms
        self.inst.write_termination = self.cfg.write_termination
        self.inst.read_termination = self.cfg.read_termination

    def close(self):
        if self.inst is not None:
            try:
                self.inst.close()
            except Exception:
                pass
        self.inst = None

    def idn(self) -> str:
        assert self.inst is not None
        return self.inst.query("*IDN?").strip()

    def measure_s21_single_freq(self, freq_hz: float) -> Tuple[float, float, float]:
        """
        Returns: (freq_hz_measured, s21_mag_db, s21_phase_deg)
        Uses the known-working approach: START=STOP, POIN 3, MARK1, OUTPMARK with LOGM/PHAS.
        """
        assert self.inst is not None
        vna = self.inst

        drain_reads(vna)

        vna.write("FORM4;")
        vna.write("S21;")

        vna.write(f"STAR {freq_hz} HZ;")
        vna.write(f"STOP {freq_hz} HZ;")
        vna.write("POIN 3;")

        vna.write(f"MARK1 {freq_hz} HZ;")

        vna.write("SING;")
        time.sleep(0.3)

        vna.write("LOGM;")
        mag_resp = vna.query("OUTPMARK;")
        mag_db, _, _ = parse_outpmark(mag_resp)

        vna.write("PHAS;")
        ph_resp = vna.query("OUTPMARK;")
        ph_deg, _, stim_hz = parse_outpmark(ph_resp)

        return stim_hz, mag_db, ph_deg


# -----------------------------
# CSV helpers
# -----------------------------

ANTENNA_FIELDNAMES = [
    "timestamp_utc",
    "angle_deg_target",
    "angle_deg_measured",
    "freq_hz_requested",
    "freq_hz_measured",
    "s21_mag_db",
    "s21_phase_deg",
]


def append_antenna_row(
    csv_path: str,
    angle_target_deg: float,
    angle_measured_deg: float,
    freq_req_hz: float,
    freq_meas_hz: float,
    mag_db: float,
    ph_deg: float,
):
    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "angle_deg_target": float(angle_target_deg),
        "angle_deg_measured": float(angle_measured_deg),
        "freq_hz_requested": float(freq_req_hz),
        "freq_hz_measured": float(freq_meas_hz),
        "s21_mag_db": float(mag_db),
        "s21_phase_deg": float(ph_deg),
    }

    try:
        with open(csv_path, "r", newline=""):
            file_exists = True
    except FileNotFoundError:
        file_exists = False

    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ANTENNA_FIELDNAMES)
        if not file_exists:
            w.writeheader()
        w.writerow(row)


# -----------------------------
# Antenna Test Mode
# -----------------------------

def antenna_test_mode(rotor: RotorController, vna: HP8720C):
    print("\n--- Antenna Test Mode ---")

    n_points = prompt_int("Number of azimuth points over 360 deg: ", min_value=1)
    freq_ghz = prompt_float("CW frequency in GHz (default 10): ", default=10.0)
    csv_path = input("CSV output file path: ").strip() or "antenna_sweep.csv"

    freq_req_hz = freq_ghz * 1e9
    step_deg = 360.0 / float(n_points)

    print(f"\nComputed:")
    print(f"  Step size = {step_deg:.6f} deg")
    print(f"  Settle check uses CP polling (tol={POS_TOL_DEG} deg, stable={STABLE_COUNT_REQUIRED} reads)\n")

    start_angle = -180.0

    # 1) Calibrate current position to -180 (no motion)
    print(f"Calibrating rotor CH{AZ_CH} position via: CP {fmt_angle(start_angle)}")
    rotor.write(AZ_CH, f"CP {fmt_angle(start_angle)}")

    # 2) Move to -180 (actual motion command)
    print(f"Moving rotor CH{AZ_CH} to start angle via: GOTO {fmt_angle(start_angle)}")
    rotor.write(AZ_CH, "SP 0")
    rotor.write(AZ_CH, f"GOTO {fmt_angle(start_angle)}")
    print("Waiting for rotor to settle at start angle...")
    pos0 = rotor.wait_until_settled(AZ_CH, start_angle)
    print(f"Settled. CP reports {pos0:.2f} deg\n")

    print(f"Sweeping {n_points} points")
    print(f"Measuring S21 at {freq_ghz:.6f} GHz")
    print(f"Saving to: {csv_path}\n")

    angle_target = start_angle

    try:
        for i in range(n_points):
            # Ensure settled at current target before measuring
            angle_meas = rotor.wait_until_settled(AZ_CH, angle_target)

            freq_meas_hz, mag_db, ph_deg = vna.measure_s21_single_freq(freq_req_hz)

            append_antenna_row(
                csv_path=csv_path,
                angle_target_deg=angle_target,
                angle_measured_deg=angle_meas,
                freq_req_hz=freq_req_hz,
                freq_meas_hz=freq_meas_hz,
                mag_db=mag_db,
                ph_deg=ph_deg,
            )

            print(
                f"[{i+1}/{n_points}] target={angle_target:.2f} deg  "
                f"meas={angle_meas:.2f} deg  "
                f"f={freq_meas_hz/1e9:.6f} GHz  S21={mag_db:.4f} dB, {ph_deg:.4f} deg"
            )

            # Next move unless final point
            if i < n_points - 1:
                angle_target = start_angle + (i + 1) * step_deg
                print(f"Moving rotor CH{AZ_CH} via: GOTO {fmt_angle(angle_target)}")
                rotor.write(AZ_CH, f"GOTO {fmt_angle(angle_target)}")

    finally:
        # Always return to 0 degrees at the end (actual motion command)
        print(f"\nReturning rotor CH{AZ_CH} to start pos via: GOTO -180")
        try:
            rotor.write(AZ_CH, "SP 2")
            rotor.write(AZ_CH, "GOTO -180")
            rotor.wait_until_settled(AZ_CH, -180)
            print("Rotor returned to start position.\n")
        except Exception as e:
            print(f"WARNING: failed to return rotor to start position: {e}\n")

    print("Antenna test mode complete.\n")


# -----------------------------
# Interactive Console
# -----------------------------

HELP_TEXT = """
Commands:

  help
    Show this help.

  rotor <ch> <w|q> <command>
    Send an arbitrary rotor command to channel ch (1-3).
    w = write only
    q = query (write then read response)
    Examples:
      rotor 2 w SP 0;
      rotor 2 w GOTO 100.00
      rotor 2 w CP -180
      rotor 2 q CP

  vna [freq_ghz]
    Run a single-point S21 measurement at freq_ghz (default 10).

  ant
    Enter antenna test mode (prompts for points/frequency/csv and runs sweep).

  status
    Show last VNA measurement (if any).

  quit
    Exit.
""".strip()


def main() -> int:
    rm = pyvisa.ResourceManager()

    rotor = RotorController(rm, DEFAULT_ROTOR)
    vna = HP8720C(rm, DEFAULT_VNA)

    last_vna: Optional[dict] = None

    try:
        rotor.open()
        vna.open()

        print("Rotor channels opened:")
        for ch, addr in DEFAULT_ROTOR.channel_to_addr.items():
            print(f"  CH{ch} -> {gpib_resource(DEFAULT_ROTOR.board, addr)}")

        print("\nVNA opened:")
        try:
            print("  ID:", vna.idn())
        except Exception as e:
            print(f"  (Could not read IDN: {e})")

        print("\n" + HELP_TEXT + "\n")

        while True:
            line = input("chamber> ").strip()
            if not line:
                continue

            parts = line.split(maxsplit=3)
            cmd = parts[0].lower()

            if cmd in {"quit", "exit", "q"}:
                break

            if cmd == "help":
                print("\n" + HELP_TEXT + "\n")
                continue

            if cmd == "status":
                if not last_vna:
                    print("No VNA measurement yet.\n")
                else:
                    print(
                        f"Last VNA: requested {last_vna['freq_req_hz']/1e9:.6f} GHz, "
                        f"measured {last_vna['freq_meas_hz']/1e9:.6f} GHz, "
                        f"S21 = {last_vna['mag_db']:.4f} dB, {last_vna['ph_deg']:.4f} deg\n"
                    )
                continue

            if cmd == "rotor":
                if len(parts) < 4:
                    print("Usage: rotor <ch> <w|q> <command>\n")
                    continue

                try:
                    ch = int(parts[1])
                    if ch not in (1, 2, 3):
                        raise ValueError
                except ValueError:
                    print("Channel must be 1, 2, or 3.\n")
                    continue

                mode = parts[2].lower()
                rotor_cmd = parts[3]

                try:
                    if mode.startswith("w"):
                        rotor.write(ch, rotor_cmd)
                        # resp = rotor.try_read_all(ch)
                        # if resp:
                        #     print(resp, "\n")
                        # else:
                        #     print("(write OK)\n")
                        print("(write OK)\n")
                    else:
                        resp = rotor.query(ch, rotor_cmd)
                        print(resp.strip(), "\n")
                except pyvisa.errors.VisaIOError as e:
                    print(f"Rotor VISA I/O error: {e}\n")
                except Exception as e:
                    print(f"Rotor error: {e}\n")
                continue

            if cmd == "vna":
                freq_ghz = 10.0
                if len(parts) >= 2:
                    try:
                        freq_ghz = float(parts[1])
                    except ValueError:
                        print("Usage: vna [freq_ghz]\n")
                        continue

                freq_req_hz = freq_ghz * 1e9

                try:
                    freq_meas_hz, mag_db, ph_deg = vna.measure_s21_single_freq(freq_req_hz)

                    if abs(freq_meas_hz - freq_req_hz) > 1e3:
                        print(f"WARNING: requested {freq_req_hz} Hz but VNA reports {freq_meas_hz} Hz")

                    print(
                        f"Measured @ {freq_meas_hz/1e9:.6f} GHz: "
                        f"S21 = {mag_db:.4f} dB, {ph_deg:.4f} deg\n"
                    )

                    last_vna = {
                        "freq_req_hz": freq_req_hz,
                        "freq_meas_hz": freq_meas_hz,
                        "mag_db": mag_db,
                        "ph_deg": ph_deg,
                    }

                except pyvisa.errors.VisaIOError as e:
                    print(f"VNA VISA I/O error: {e}\n")
                except Exception as e:
                    print(f"VNA error: {e}\n")
                continue

            if cmd in {"ant", "antenna"}:
                try:
                    antenna_test_mode(rotor, vna)
                except pyvisa.errors.VisaIOError as e:
                    print(f"Antenna mode VISA I/O error: {e}\n")
                except Exception as e:
                    print(f"Antenna mode error: {e}\n")
                continue

            print("Unknown command. Type 'help' for options.\n")

    finally:
        try:
            rotor.close()
        except Exception:
            pass
        try:
            vna.close()
        except Exception:
            pass
        try:
            rm.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())