#!/usr/bin/env python3

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


def plot_folder(folder_path: str):
    folder = Path(folder_path)

    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    csv_files = sorted(folder.glob("*.csv"))

    if not csv_files:
        print("No CSV files found.")
        return

    for csv_file in csv_files:
        df = pd.read_csv(csv_file)

        required_cols = {"angle_deg_target", "s21_mag_db"}
        if not required_cols.issubset(df.columns):
            print(f"Skipping {csv_file.name}: missing required columns")
            continue

        df = df.sort_values("angle_deg_target")

        label = csv_file.stem

        angles_deg = df["angle_deg_target"].values + 90
        theta = np.deg2rad(angles_deg)

        r = df["s21_mag_db"].values

        peak_idx = np.argmax(r)
        print(
            f"{csv_file.name}: peak at {angles_deg[peak_idx]:.2f} deg, "
            f"{r[peak_idx]:.2f} dB"
        )

        fig = plt.figure()
        ax = fig.add_subplot(111, projection="polar")

        ax.plot(theta, r)
        ax.set_title(f"S21 Pattern (dB) - {label}")
        ax.set_rlabel_position(135)
        ax.grid(True)

        ax.set_theta_zero_location("N")

    plt.show()


def main():
    folder_path = input("Enter folder path containing antenna sweep CSV files: ").strip()
    plot_folder(folder_path)


if __name__ == "__main__":
    main()