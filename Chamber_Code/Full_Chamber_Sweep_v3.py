#!/usr/bin/env python3

from __future__ import annotations

import cmath
import csv
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import pyvisa
import requests


@dataclass(frozen=True)
class RotorConfig:
    board: int = 0
    channel_to_addr: dict[int, int] = None
    timeout_ms: int = 6000
    write_termination: str = "\n"
    read_termination: str = "\n"


@dataclass(frozen=True)
class VNAConfig:
    resource: str = "GPIB0::16::INSTR"
    timeout_ms: int = 10000
    write_termination: str = "\n"
    read_termination: str = "\n"


DEFAULT_ROTOR = RotorConfig(channel_to_addr={1: 20, 2: 21, 3: 22})
DEFAULT_VNA = VNAConfig()

AZ_CH = 2

POS_TOL_DEG = 1.0
STABLE_COUNT_REQUIRED = 3
POLL_INTERVAL_S = 0.25
MAX_WAIT_S = 120.0


def gpib_resource(board: int, primary_addr: int) -> str:
    return f"GPIB{board}::{primary_addr}::INSTR"


def safe_timeout_read(inst) -> Optional[str]:
    try:
        return inst.read()
    except pyvisa.errors.VisaIOError as e:
        if e.error_code == pyvisa.constants.StatusCode.error_timeout:
            return None
        raise


def prompt_yes_no(prompt: str) -> bool:
    while True:
        raw = input(prompt).strip().lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please enter yes or no.")


def prompt_int(prompt: str, min_value: int = 1, max_value: Optional[int] = None) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
            if value < min_value:
                print(f"Value must be >= {min_value}.")
                continue
            if max_value is not None and value > max_value:
                print(f"Value must be <= {max_value}.")
                continue
            return value
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


def prompt_sweep_span_deg() -> float:
    while True:
        raw = input("Sweep range in degrees (enter 180 or 360): ").strip()
        if raw in {"180", "180.0"}:
            return 180.0
        if raw in {"360", "360.0"}:
            return 360.0
        print("Please enter either 180 or 360.")


def prompt_sweep_mode() -> str:
    while True:
        raw = input("Sweep mode: simple or eh? ").strip().lower()
        if raw in {"simple", "s"}:
            return "simple"
        if raw in {"eh", "e/h", "e-h"}:
            return "eh"
        print("Please enter 'simple' or 'eh'.")


def fmt_angle(angle_deg: float) -> str:
    return f"{angle_deg:.2f}"


def parse_first_float(text: str) -> float:
    s = text.strip()
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


def send_ntfy_notification(topic: str, message: str):
    try:
        response = requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            timeout=10,
        )
        response.raise_for_status()
        print("ntfy notification sent.")
    except Exception as e:
        print(f"WARNING: failed to send ntfy notification: {e}")


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

    def get_position_deg(self, ch: int) -> float:
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
        stable = 0
        last_pos = None
        t0 = time.time()

        while True:
            if time.time() - t0 > max_wait_s:
                raise TimeoutError(
                    f"Rotor CH{ch} did not settle to {target_deg:.2f} deg "
                    f"within {max_wait_s:.1f} s. Last position: {last_pos}"
                )

            try:
                pos = self.get_position_deg(ch)
                last_pos = pos
            except Exception:
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

    def goto_and_wait(self, ch: int, angle_deg: float) -> float:
        print(f"Moving rotor CH{ch} via: GOTO {fmt_angle(angle_deg)}")
        self.write(ch, f"GOTO {fmt_angle(angle_deg)}")
        pos = self.wait_until_settled(ch, angle_deg)
        print(f"Rotor CH{ch} settled at {pos:.2f} deg")
        return pos

    def move_to_starting_positions(self):
        print("\nMoving positioners to starting positions:")
        self.goto_and_wait(1, 0.0)

        print("Setting azimuth speed for move to start: SP 0")
        self.write(AZ_CH, "SP 0")
        self.goto_and_wait(2, -180.0)

        self.goto_and_wait(3, 0.0)


def parse_outpmark(resp: str) -> tuple[float, float, float]:
    parts = [p.strip() for p in resp.strip().split(",") if p.strip()]
    if len(parts) < 3:
        raise ValueError(f"Unexpected OUTPMARK response: {resp!r}")
    return float(parts[0]), float(parts[1]), float(parts[2])


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
        assert self.inst is not None
        vna = self.inst

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


def average_s21_measurements(vna: HP8720C, freq_req_hz: float, n_avg: int):
    complex_vals = []
    freq_vals = []

    for _ in range(n_avg):
        freq_meas_hz, mag_db, phase_deg = vna.measure_s21_single_freq(freq_req_hz)

        mag_linear = 10 ** (mag_db / 20.0)
        phase_rad = math.radians(phase_deg)
        complex_val = mag_linear * cmath.exp(1j * phase_rad)

        complex_vals.append(complex_val)
        freq_vals.append(freq_meas_hz)

    avg_complex = sum(complex_vals) / len(complex_vals)

    avg_mag_db = 20.0 * math.log10(abs(avg_complex))
    avg_phase_deg = math.degrees(cmath.phase(avg_complex))
    avg_freq_hz = sum(freq_vals) / len(freq_vals)

    return avg_freq_hz, avg_mag_db, avg_phase_deg


ANTENNA_FIELDNAMES = [
    "timestamp_utc",
    "sweep_label",
    "sweep_span_deg",
    "s21_averages",
    "angle_deg_target",
    "angle_deg_measured",
    "freq_hz_requested",
    "freq_hz_measured",
    "s21_mag_db",
    "s21_phase_deg",
]


def append_antenna_row(
    csv_path: str | Path,
    sweep_label: str,
    sweep_span_deg: float,
    n_avg: int,
    angle_target_deg: float,
    angle_measured_deg: float,
    freq_req_hz: float,
    freq_meas_hz: float,
    mag_db: float,
    ph_deg: float,
):
    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sweep_label": sweep_label,
        "sweep_span_deg": float(sweep_span_deg),
        "s21_averages": int(n_avg),
        "angle_deg_target": float(angle_target_deg),
        "angle_deg_measured": float(angle_measured_deg),
        "freq_hz_requested": float(freq_req_hz),
        "freq_hz_measured": float(freq_meas_hz),
        "s21_mag_db": float(mag_db),
        "s21_phase_deg": float(ph_deg),
    }

    csv_path = Path(csv_path)
    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ANTENNA_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def run_single_azimuth_sweep(
    rotor: RotorController,
    vna: HP8720C,
    sweep_label: str,
    sweep_span_deg: float,
    n_points: int,
    freq_req_hz: float,
    csv_path: str | Path,
    n_avg: int,
):
    start_angle = -180.0
    step_deg = sweep_span_deg / float(n_points)

    print(f"\n--- Running {sweep_label} sweep ---")
    print(f"CSV: {csv_path}")
    print(f"Sweep span: {sweep_span_deg:.0f} deg")
    print(f"Points: {n_points}")
    print(f"Step size: {step_deg:.6f} deg")
    print(f"Averages per angle: {n_avg}")
    print(f"Start angle: {start_angle:.2f} deg\n")

    print("Setting azimuth speed for sweep: SP 0")
    rotor.write(AZ_CH, "SP 0")

    rotor.goto_and_wait(AZ_CH, start_angle)

    angle_target = start_angle

    for i in range(n_points):
        angle_meas = rotor.wait_until_settled(AZ_CH, angle_target)

        freq_meas_hz, mag_db, ph_deg = average_s21_measurements(
            vna=vna,
            freq_req_hz=freq_req_hz,
            n_avg=n_avg,
        )

        append_antenna_row(
            csv_path=csv_path,
            sweep_label=sweep_label,
            sweep_span_deg=sweep_span_deg,
            n_avg=n_avg,
            angle_target_deg=angle_target,
            angle_measured_deg=angle_meas,
            freq_req_hz=freq_req_hz,
            freq_meas_hz=freq_meas_hz,
            mag_db=mag_db,
            ph_deg=ph_deg,
        )

        print(
            f"[{i + 1}/{n_points}] {sweep_label}  "
            f"target={angle_target:.2f} deg  "
            f"meas={angle_meas:.2f} deg  "
            f"f={freq_meas_hz / 1e9:.6f} GHz  "
            f"S21_avg={mag_db:.4f} dB, {ph_deg:.4f} deg"
        )

        if i < n_points - 1:
            next_angle = start_angle + (i + 1) * step_deg

            if next_angle > 180.0:
                next_angle = 180.0

            rotor.goto_and_wait(AZ_CH, next_angle)
            angle_target = next_angle

    print(f"\nReturning azimuth rotor CH{AZ_CH} to -180 deg after {sweep_label} sweep.")
    rotor.write(AZ_CH, "SP 2")
    rotor.goto_and_wait(AZ_CH, -180.0)


def antenna_test_mode(rotor: RotorController, vna: HP8720C):
    print("\n--- Antenna Test Mode ---")

    notify_enabled = prompt_yes_no("Send ntfy phone notification when sweep completes? (yes/no): ")
    ntfy_topic = ""

    if notify_enabled:
        ntfy_topic = input("Enter ntfy topic name: ").strip()

    sweep_mode = prompt_sweep_mode()
    sweep_span_deg = prompt_sweep_span_deg()
    max_points = 180 if sweep_span_deg == 180.0 else 360

    n_points = prompt_int(
        f"Number of azimuth points over {int(sweep_span_deg)} deg "
        f"(max {max_points}): ",
        min_value=1,
        max_value=max_points,
    )

    freq_ghz = prompt_float("CW frequency in GHz (default 10): ", default=10.0)
    freq_req_hz = freq_ghz * 1e9

    n_avg = prompt_int(
        "Number of S21 averages per azimuth angle (1 to 10): ",
        min_value=1,
        max_value=10,
    )

    sweep_status = "completed"

    try:
        rotor.move_to_starting_positions()

        if sweep_mode == "simple":
            csv_path = input("CSV output file path: ").strip() or "antenna_sweep.csv"

            run_single_azimuth_sweep(
                rotor=rotor,
                vna=vna,
                sweep_label="simple",
                sweep_span_deg=sweep_span_deg,
                n_points=n_points,
                freq_req_hz=freq_req_hz,
                csv_path=csv_path,
                n_avg=n_avg,
            )

        else:
            test_name = input("Test name for E/H sweep: ").strip() or "antenna_test"
            folder_raw = input("Folder path for E/H CSV files: ").strip()
            folder = Path(folder_raw) if folder_raw else Path(".")
            folder.mkdir(parents=True, exist_ok=True)

            csv_paths = {
                "EE": folder / f"{test_name}_EE.csv",
                "HE": folder / f"{test_name}_HE.csv",
                "HH": folder / f"{test_name}_HH.csv",
                "EH": folder / f"{test_name}_EH.csv",
            }

            print("\nE/H sweep CSV files:")
            for label, path in csv_paths.items():
                print(f"  {label}: {path}")

            run_single_azimuth_sweep(
                rotor=rotor,
                vna=vna,
                sweep_label="EE",
                sweep_span_deg=sweep_span_deg,
                n_points=n_points,
                freq_req_hz=freq_req_hz,
                csv_path=csv_paths["EE"],
                n_avg=n_avg,
            )

            rotor.goto_and_wait(1, 90.0)

            run_single_azimuth_sweep(
                rotor=rotor,
                vna=vna,
                sweep_label="HE",
                sweep_span_deg=sweep_span_deg,
                n_points=n_points,
                freq_req_hz=freq_req_hz,
                csv_path=csv_paths["HE"],
                n_avg=n_avg,
            )

            rotor.goto_and_wait(3, 90.0)

            run_single_azimuth_sweep(
                rotor=rotor,
                vna=vna,
                sweep_label="HH",
                sweep_span_deg=sweep_span_deg,
                n_points=n_points,
                freq_req_hz=freq_req_hz,
                csv_path=csv_paths["HH"],
                n_avg=n_avg,
            )

            rotor.goto_and_wait(1, 0.0)

            run_single_azimuth_sweep(
                rotor=rotor,
                vna=vna,
                sweep_label="EH",
                sweep_span_deg=sweep_span_deg,
                n_points=n_points,
                freq_req_hz=freq_req_hz,
                csv_path=csv_paths["EH"],
                n_avg=n_avg,
            )

    except Exception as e:
        sweep_status = "FAILED"

        if notify_enabled and ntfy_topic:
            send_ntfy_notification(
                topic=ntfy_topic,
                message=f"Antenna sweep FAILED:\n{str(e)}",
            )

        raise

    finally:
        print("\nReturning positioners to starting positions.")
        try:
            rotor.goto_and_wait(1, 0.0)
        except Exception as e:
            print(f"WARNING: failed to return rotor CH1 to 0 deg: {e}")

        try:
            rotor.write(AZ_CH, "SP 2")
            rotor.goto_and_wait(2, -180.0)
        except Exception as e:
            print(f"WARNING: failed to return rotor CH2 to -180 deg: {e}")

        try:
            rotor.goto_and_wait(3, 0.0)
        except Exception as e:
            print(f"WARNING: failed to return rotor CH3 to 0 deg: {e}")

        if notify_enabled and ntfy_topic and sweep_status == "completed":
            send_ntfy_notification(
                topic=ntfy_topic,
                message=(
                    "Antenna sweep complete\n"
                    f"Mode: {sweep_mode}\n"
                    f"Span: {sweep_span_deg:.0f} deg\n"
                    f"Points: {n_points}\n"
                    f"Averages: {n_avg}\n"
                    f"Freq: {freq_ghz:.6f} GHz"
                ),
            )

    print("\nAntenna test mode complete.\n")


HELP_TEXT = """
Commands:

  help
    Show this help.

  rotor <ch> <w|q> <command>
    Send an arbitrary rotor command to channel ch (1-3).

  vna [freq_ghz]
    Run a single-point S21 measurement at freq_ghz.

  ant
    Enter antenna test mode.

  status
    Show last VNA measurement.

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
        print("  ID:", vna.idn())

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
                    print(last_vna, "\n")
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
                        print("(write OK)\n")
                    else:
                        print(rotor.query(ch, rotor_cmd).strip(), "\n")
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

                    print(
                        f"Measured @ {freq_meas_hz / 1e9:.6f} GHz: "
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

            print("Unknown command. Type 'help'.\n")

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