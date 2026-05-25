import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

csv_file = "C:/Users/Armin Behbahani/Documents/Thesis/RA_UC_Ring_Raw_Data/third_wavelength_cell/Report_Plots/third_wavelength_RO4350b_3,00-9,746mm_all_thicknesses.csv"

h_col = "$H [mm]"
l_col = "$Lpatch [mm]"
phase_col = "ang_deg(St(FloquetPort1:1,FloquetPort1:1)) [deg]"

df = pd.read_csv(csv_file)

df[h_col] = pd.to_numeric(df[h_col], errors="coerce")
df[l_col] = pd.to_numeric(df[l_col], errors="coerce")
df[phase_col] = pd.to_numeric(df[phase_col], errors="coerce")

df = df.dropna(subset=[h_col, l_col, phase_col])
df = df.sort_values(by=[h_col, l_col])

def unwrap_decreasing_phase(phase_deg, jump_threshold=60):
    """
    Custom unwrap for reflectarray phase curves that should generally decrease.
    """

    phase_fixed = phase_deg.copy().astype(float)

    for i in range(1, len(phase_fixed)):
        jump = phase_fixed[i] - phase_fixed[i - 1]

        # A sudden upward jump is probably a wrap
        if jump > jump_threshold:
            phase_fixed[i:] -= 360

    return phase_fixed

plt.figure(figsize=(8, 5))

print("Total unwrapped phase-shift range for each data set:")
print("-" * 55)

for H, group in df.groupby(h_col):
    group = group.sort_values(by=l_col)

    L = group[l_col].to_numpy()
    phase_deg = group[phase_col].to_numpy()

    phase_unwrapped = unwrap_decreasing_phase(
        phase_deg,
        jump_threshold=60
    )

    # Total phase shift range
    phase_range = np.max(phase_unwrapped) - np.min(phase_unwrapped)

    print(f"H_D = {H:g} mm: {phase_range:.2f} deg")

    plt.plot(
        L,
        phase_unwrapped,
        linewidth=1.5,
        label=f"H = {H:g} mm"
    )

plt.xlabel("Patch Length, $L_{patch}$ [mm]",
           fontweight='bold'
           )
plt.ylabel("Unwrapped Reflection Phase [deg]",
           fontweight='bold'
           )
plt.title("Third-wavelength Patch S-Curve vs. $H_{D}$")
plt.grid(True)
plt.legend(title="$H_{D}$ [mm]")
plt.tight_layout()
plt.show()