import numpy as np
import matplotlib.pyplot as plt

# -----------------------------
# Spherical coordinate grid
# -----------------------------
theta = np.linspace(0, np.pi, 250)        # theta: polar angle, 0 to pi
phi = np.linspace(0, 2*np.pi, 250)        # phi: azimuth angle, 0 to 2pi
theta, phi = np.meshgrid(theta, phi)

# -----------------------------
# Radiation pattern r(theta, phi)
# -----------------------------

# Main lobe along +z direction, theta = 0
main_lobe = np.cos(theta / 2)**18

# Side lobes
side_lobes = 0.08 * (np.sin(3*theta)**2) * (np.cos(4*phi)**2)

# Small rear lobe along -z direction, theta = pi
rear_lobe = 0.01 * np.sin(theta / 2)**22

# Total pattern
r = main_lobe + side_lobes + rear_lobe
r = r / np.max(r)

# -----------------------------
# Convert spherical to Cartesian
# Needed only for 3D rendering
# -----------------------------
x = r * np.sin(theta) * np.cos(phi)
y = r * np.sin(theta) * np.sin(phi)
z = r * np.cos(theta)

# -----------------------------
# Plot
# -----------------------------
fig = plt.figure(figsize=(8, 8))
ax = fig.add_subplot(111, projection="3d")

surf = ax.plot_surface(
    x, y, z,
    cmap="viridis",
    linewidth=0,
    antialiased=True,
    alpha=0.45
)

# -----------------------------
# Add spherical coordinate guide rings
# -----------------------------

# Unit sphere guide rings
ring_phi = np.linspace(0, 2*np.pi, 400)

# xy-plane ring, theta = 90 deg
x_ring = np.cos(ring_phi)
y_ring = np.sin(ring_phi)
z_ring = np.zeros_like(ring_phi)
ax.plot(x_ring, y_ring, z_ring, linestyle="--", linewidth=1)

# xz-plane ring, phi = 0 deg
x_ring = np.sin(ring_phi)
y_ring = np.zeros_like(ring_phi)
z_ring = np.cos(ring_phi)
ax.plot(x_ring, y_ring, z_ring, linestyle="--", linewidth=1)

# yz-plane ring, phi = 90 deg
x_ring = np.zeros_like(ring_phi)
y_ring = np.sin(ring_phi)
z_ring = np.cos(ring_phi)
ax.plot(x_ring, y_ring, z_ring, linestyle="--", linewidth=1)

# -----------------------------
# Labels and formatting
# -----------------------------
ax.set_title("3D Radiation Pattern in Spherical Coordinates", pad=20)

ax.set_xlabel(r"$x = r\sin\theta\cos\phi$")
ax.set_ylabel(r"$y = r\sin\theta\sin\phi$")
ax.set_zlabel(r"$z = r\cos\theta$")

ax.text(0, 0, 1.15, r"$\theta = 0^\circ$", ha="center")
ax.text(0, 0, -1.15, r"$\theta = 180^\circ$", ha="center")
ax.text(1.15, 0, 0, r"$\phi = 0^\circ$", ha="center")
ax.text(0, 1.15, 0, r"$\phi = 90^\circ$", ha="center")

ax.set_box_aspect([1, 1, 1])

# Set equal limits
limit = 1.1
ax.set_xlim(-limit, limit)
ax.set_ylim(-limit, limit)
ax.set_zlim(-limit, limit)

fig.colorbar(surf, ax=ax, shrink=0.65, label="Normalized Radiation Magnitude")

plt.show()