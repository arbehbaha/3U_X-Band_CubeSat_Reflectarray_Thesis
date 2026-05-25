import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


#################################################
#   USER SETTINGS
#################################################

data_folder = Path(r"RA_EH_Sweep_5-3-2026")

pattern_colors = {
    "EE": "red",
    "EH": "blue",
    "HE": "green",
    "HH": "purple",
}

plot_order = ["EE", "EH", "HE", "HH"]
co_pol_patterns = ["EE", "HH"]


#################################################
#   HELPER FUNCTIONS
#################################################

def identify_pattern_type(file_name):
    """
    Identifies EE, EH, HE, or HH from the final token of the filename.

    Example:
    RA_EH_Sweep_10GHz_360pt_HE.csv -> HE
    """

    stem = Path(file_name).stem.upper()
    pattern_type = stem.split("_")[-1]

    if pattern_type in ["EE", "EH", "HE", "HH"]:
        return pattern_type

    return None


def clean_columns(df):
    """
    Cleans column names by removing hidden characters,
    extra spaces, and quotation marks.
    """

    df.columns = (
        df.columns
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
        .str.replace('"', "", regex=False)
    )

    return df


def load_pattern_csv(file_path):
    """
    Loads one radiation pattern CSV file.
    """

    df = pd.read_csv(file_path)
    df = clean_columns(df)

    required_columns = ["angle_deg_measured", "s21_mag_db"]

    for col in required_columns:
        if col not in df.columns:
            raise KeyError(
                f"Required column '{col}' was not found in {file_path.name}.\n"
                f"Available columns: {df.columns.tolist()}"
            )

    df = df.sort_values("angle_deg_measured").copy()

    return df


def wrap_angle_deg(angle):
    """
    Wraps angles to [-180, 180].
    """

    return ((angle + 180) % 360) - 180


def find_3db_points(angle, gain):
    """
    Finds the -3 dB points on both sides of the main peak.

    The gain array should already be normalized using the global reference.
    The function finds the local peak of this dataset and then finds
    where the curve drops by 3 dB on either side.
    """

    peak_idx = np.argmax(gain)
    peak_gain = gain[peak_idx]
    target_gain = peak_gain - 3.0

    left_angle = None
    right_angle = None

    # Search left side of peak
    for i in range(peak_idx, 0, -1):
        if gain[i] >= target_gain and gain[i - 1] <= target_gain:
            x1, y1 = angle[i - 1], gain[i - 1]
            x2, y2 = angle[i], gain[i]

            left_angle = x1 + (target_gain - y1) * (x2 - x1) / (y2 - y1)
            break

    # Search right side of peak
    for i in range(peak_idx, len(gain) - 1):
        if gain[i] >= target_gain and gain[i + 1] <= target_gain:
            x1, y1 = angle[i], gain[i]
            x2, y2 = angle[i + 1], gain[i + 1]

            right_angle = x1 + (target_gain - y1) * (x2 - x1) / (y2 - y1)
            break

    return left_angle, right_angle, target_gain


#################################################
#   LOAD ALL DATASETS
#################################################

csv_files = sorted(data_folder.glob("*.csv"))

if not csv_files:
    raise FileNotFoundError(f"No CSV files found in folder: {data_folder}")

patterns = {}

for file_path in csv_files:
    pattern_type = identify_pattern_type(file_path.name)

    if pattern_type is None:
        print(f"Skipping unrecognized file: {file_path.name}")
        continue

    df = load_pattern_csv(file_path)

    patterns[pattern_type] = {
        "file_name": file_path.name,
        "df": df,
        "angle": df["angle_deg_measured"],
        "s21": df["s21_mag_db"],
    }

    print(f"Loaded {pattern_type}: {file_path.name}")

if "EE" not in patterns:
    raise FileNotFoundError(
        "No EE dataset was found. An EE file is required to center the angular axis."
    )


#################################################
#   DETERMINE EE CENTERING OFFSET
#################################################

ee_angle = patterns["EE"]["angle"]
ee_s21 = patterns["EE"]["s21"]

ee_peak_idx = ee_s21.idxmax()
ee_peak_angle = ee_angle.loc[ee_peak_idx]

print(f"\nEE peak angle used for centering: {ee_peak_angle:.2f} degrees")


#################################################
#   DETERMINE GLOBAL NORMALIZATION OFFSET
#################################################

global_peak_pattern = max(
    patterns.keys(),
    key=lambda p: patterns[p]["s21"].max()
)

global_peak_value = patterns[global_peak_pattern]["s21"].max()

print(
    f"Global peak used for normalization: "
    f"{global_peak_value:.2f} dB from {global_peak_pattern}"
)


#################################################
#   PROCESS DATASETS
#################################################

for pattern_type, data in patterns.items():
    df = data["df"].copy()

    # Shift all patterns using the EE peak angle only
    df["angle_adjusted"] = wrap_angle_deg(
        df["angle_deg_measured"] - ee_peak_angle
    )

    # Normalize all patterns using the same global peak value
    df["s21_normalized"] = df["s21_mag_db"] - global_peak_value

    df = df.sort_values("angle_adjusted").copy()

    patterns[pattern_type]["angle_plot"] = df["angle_adjusted"].to_numpy()
    patterns[pattern_type]["s21_plot"] = df["s21_normalized"].to_numpy()


#################################################
#   PLOT EACH DATASET IN ITS OWN FIGURE
#################################################

for pattern_type in plot_order:
    if pattern_type not in patterns:
        continue

    angle_plot = patterns[pattern_type]["angle_plot"]
    s21_plot = patterns[pattern_type]["s21_plot"]
    color = pattern_colors[pattern_type]

    plt.figure(figsize=(9, 6))

    plt.plot(
        angle_plot,
        s21_plot,
        color=color,
        linewidth=2,
        label=f"{pattern_type} Radiation Pattern"
    )

        # Add -3 dB points only for EE and HH
        # Add -3 dB points and calculate beamwidth only for EE and HH
    if pattern_type in co_pol_patterns:
        left_angle, right_angle, target_gain = find_3db_points(
            angle_plot,
            s21_plot
        )

        if left_angle is not None:
            plt.scatter(
                left_angle,
                target_gain,
                color=color,
                edgecolor="black",
                marker="v",
                zorder=5,
                label=rf"Lower -3 dB Point: $\theta$ = {left_angle:.2f}°"
            )

        if right_angle is not None:
            plt.scatter(
                right_angle,
                target_gain,
                color=color,
                edgecolor="black",
                marker="^",
                zorder=5,
                label=rf"Upper -3 dB Point: $\theta$ = {right_angle:.2f}°"
            )

        if left_angle is not None and right_angle is not None:
            beamwidth_3db = right_angle - left_angle

            print("\n" + "-" * 50)
            print(f"{pattern_type} 3-dB Beamwidth Results")
            print("-" * 50)
            print(f"Lower -3 dB angle: {left_angle:.2f} deg")
            print(f"Upper -3 dB angle: {right_angle:.2f} deg")
            print(f"3-dB beamwidth:     {beamwidth_3db:.2f} deg")
            print("-" * 50)

        else:
            print(f"{pattern_type}: Could not determine both -3 dB points.")

    #################################################
    #   FORMAT INDIVIDUAL PLOT
    #################################################

    plt.xlabel("Angle [deg]", fontsize=12, fontweight="bold")
    plt.ylabel(
        r"Normalized $S_{21}$ Magnitude [dB]",
        fontsize=12,
        fontweight="bold"
    )

    plt.title(
        rf"{pattern_type} Normalized Radiation Pattern vs. Angle",
        fontsize=14,
        fontweight="bold"
    )

    plt.xlim(-180, 180)
    plt.ylim(bottom=-60, top=5)

    plt.legend()
    plt.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.show()