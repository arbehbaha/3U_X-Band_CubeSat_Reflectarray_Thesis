import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from matplotlib.lines import Line2D

# Load CSV file
file_path = r"Full_RA_Simulation_Data\Gain Plot_2D.csv"
df = pd.read_csv(file_path)

# Extract frequency
freq = df["Freq [GHz]"].iloc[0]

# Separate polarization angle cuts
df_pol0 = df[df["Phi [deg]"] == 0].copy()
df_pol90 = df[df["Phi [deg]"].round() == 90].copy()

# Sort by theta to make peak detection reliable
df_pol0 = df_pol0.sort_values("Theta [deg]")
df_pol90 = df_pol90.sort_values("Theta [deg]")

theta0_original = df_pol0["Theta [deg]"].to_numpy()
gain0 = df_pol0["dB(GainTotal) []"].to_numpy()

# Find local peaks for 0-degree case
peak_indices, _ = find_peaks(gain0)

# Sort local peaks by gain, highest first
top_peak_indices = peak_indices[gain0[peak_indices].argsort()[::-1]]

# Highest peak = main lobe
main_lobe_idx = top_peak_indices[0]

# Original main lobe angle
main_peak_theta_original = theta0_original[main_lobe_idx]

# Shift theta so the main peak is at 0 degrees
theta_offset = main_peak_theta_original

df_pol0["Theta Adjusted [deg]"] = df_pol0["Theta [deg]"] - theta_offset
df_pol90["Theta Adjusted [deg]"] = df_pol90["Theta [deg]"] - theta_offset

# Wrap adjusted theta to [-180, 180]
df_pol0["Theta Adjusted [deg]"] = (
    (df_pol0["Theta Adjusted [deg]"] + 180) % 360
) - 180

df_pol90["Theta Adjusted [deg]"] = (
    (df_pol90["Theta Adjusted [deg]"] + 180) % 360
) - 180

# Re-sort by adjusted theta for cleaner plotting
df_pol0 = df_pol0.sort_values("Theta Adjusted [deg]")
df_pol90 = df_pol90.sort_values("Theta Adjusted [deg]")

theta0 = df_pol0["Theta Adjusted [deg]"].to_numpy()
gain0 = df_pol0["dB(GainTotal) []"].to_numpy()

# Recalculate peaks after sorting by adjusted theta
peak_indices, _ = find_peaks(gain0)
top_peak_indices = peak_indices[gain0[peak_indices].argsort()[::-1]]

main_lobe_idx = top_peak_indices[0]
side_lobe_indices = top_peak_indices[1:4]

# Main lobe peak
main_peak_theta = theta0[main_lobe_idx]
main_peak_gain = gain0[main_lobe_idx]

# ---------------------------------------------------------
# Calculate 3 dB beamwidth for the 0-degree cut
# ---------------------------------------------------------
half_power_gain = main_peak_gain - 3.0

# Search left side of main lobe
left_idx = main_lobe_idx
while left_idx > 0 and gain0[left_idx] >= half_power_gain:
    left_idx -= 1

# Search right side of main lobe
right_idx = main_lobe_idx
while right_idx < len(gain0) - 1 and gain0[right_idx] >= half_power_gain:
    right_idx += 1

# Linear interpolation to estimate exact -3 dB crossing points
theta_left_3db = np.interp(
    half_power_gain,
    [gain0[left_idx], gain0[left_idx + 1]],
    [theta0[left_idx], theta0[left_idx + 1]]
)

theta_right_3db = np.interp(
    half_power_gain,
    [gain0[right_idx], gain0[right_idx - 1]],
    [theta0[right_idx], theta0[right_idx - 1]]
)

beamwidth_3db = theta_right_3db - theta_left_3db

print(f"Main peak gain: {main_peak_gain:.2f} dB")
print(f"Half-power level: {half_power_gain:.2f} dB")
print(f"Left -3 dB angle: {theta_left_3db:.2f} deg")
print(f"Right -3 dB angle: {theta_right_3db:.2f} deg")
print(f"3 dB beamwidth: {beamwidth_3db:.2f} deg")

# Create plot
fig, ax = plt.subplots(figsize=(8, 5))

line0, = ax.plot(
    df_pol0["Theta Adjusted [deg]"],
    df_pol0["dB(GainTotal) []"],
    color="red",
    linewidth=2,
    label=r"$0^\circ$"
)

line90, = ax.plot(
    df_pol90["Theta Adjusted [deg]"],
    df_pol90["dB(GainTotal) []"],
    color="blue",
    linewidth=2,
    label=r"$90^\circ$"
)

# Mark and label the main lobe peak
ax.scatter(
    main_peak_theta,
    main_peak_gain,
    color="red",
    edgecolor="black",
    zorder=5
)

ax.annotate(
    f"Peak: {main_peak_gain:.2f} dB\n$\\theta$ = {main_peak_theta:.1f}°",
    xy=(main_peak_theta, main_peak_gain),
    xytext=(main_peak_theta - 85, main_peak_gain - 3),
    arrowprops=dict(arrowstyle="->", color="red"),
    fontsize=10,
    fontweight="bold",
    color="red"
)

# Draw -3 dB beamwidth markers
ax.axhline(
    y=half_power_gain,
    color="black",
    linestyle="--",
    linewidth=1.2,
    label="-3 dB level"
)

ax.axvline(
    x=theta_left_3db,
    color="black",
    linestyle=":",
    linewidth=1.2
)

ax.axvline(
    x=theta_right_3db,
    color="black",
    linestyle=":",
    linewidth=1.2
)

ax.annotate(
    f"3 dB BW = {beamwidth_3db:.2f}°",
    xy=(0, half_power_gain),
    xytext=(10, half_power_gain - 5),
    arrowprops=dict(arrowstyle="->", color="black"),
    fontsize=10,
    fontweight="bold",
    color="black"
)

# Mark the prominent side lobes and list them in a separate legend
peak_handles = []

for rank, idx in enumerate(side_lobe_indices, start=1):
    side_lobe_theta = theta0[idx]
    side_lobe_gain = gain0[idx]

    ax.scatter(
        side_lobe_theta,
        side_lobe_gain,
        color="red",
        edgecolor="black",
        zorder=5
    )

    peak_handles.append(
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="red",
            markeredgecolor="black",
            markersize=7,
            label=(
                f"Side Lobe {rank}: {side_lobe_gain:.2f} dB, "
                rf"$\theta$ = {side_lobe_theta:.1f}°"
            )
        )
    )

ax.set_xlabel("Adjusted Theta [deg]", fontsize=12, fontweight="bold")
ax.set_ylabel("Gain [dB]", fontsize=12, fontweight="bold")
ax.set_title(
    f"2D Elevation Radiation Pattern at {freq} GHz",
    fontsize=14,
    fontweight="bold"
)

ax.set_xlim(-180, 180)

# Main legend for polarization angle
legend1 = ax.legend(
    handles=[line0, line90],
    title="Polarization Angle",
    title_fontsize=11,
    loc="upper left"
)
ax.add_artist(legend1)

# Separate legend for side-lobe data
legend2 = ax.legend(
    handles=peak_handles,
    title="Prominent Side Lobes",
    title_fontsize=11,
    loc="upper right"
)

legend2.get_title().set_fontweight("bold")

ax.grid(True, alpha=0.4)
plt.tight_layout()
plt.show()