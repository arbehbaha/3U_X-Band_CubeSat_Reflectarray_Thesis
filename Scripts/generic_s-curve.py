import numpy as np
import matplotlib.pyplot as plt

# Patch length range
L = np.linspace(2.0, 8.0, 500)
L_points = np.arange(2.0, 8.0 + 0.5, 0.3)

# S-curve parameters
L0 = 5.0
phase_center = 180.0
phase_span = 390.0

# Slopes and subplot titles
midpoint_slopes = [-400.0, -200.0]
subplot_titles = ["Large Phase Slope", "Small Phase Slope"]

A = phase_span / 2.0

fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharex=True, sharey=True)

for ax, midpoint_slope, subplot_title in zip(axes, midpoint_slopes, subplot_titles):

    k = midpoint_slope * np.pi / (2.0 * A)

    phase = phase_center + A * (2.0 / np.pi) * np.arctan(k * (L - L0))
    phase_points = phase_center + A * (2.0 / np.pi) * np.arctan(k * (L_points - L0))

    ax.plot(L, phase)
    ax.plot(L_points, phase_points, "o")

    ax.set_xlim(2.0, 8.0)
    ax.set_ylim(0.0, 360.0)

    ax.axhline(y=50, color="red", linestyle="--")
    ax.axhline(y=300, color="red", linestyle="--")

    ax.set_xlabel("Patch length L", fontsize=12)
    ax.set_title(subplot_title)

    ax.grid(True)

axes[0].set_ylabel("Reflection phase (degrees)", fontsize=12)

fig.suptitle("Example S-Curve Phase-Gradient Comparison", 
             fontsize=15,
             fontweight = 'bold'
             )

fig.text(
    0.5, 0.92,
    "Patch Length Increment = 0.3L",
    ha="center",
    fontsize=15,
    color = "gray"
)
plt.tight_layout()
plt.show()