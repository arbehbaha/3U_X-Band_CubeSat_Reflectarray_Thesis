import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def plot_3d_arrow(
    ax,
    start,
    end,
    radius=0.35,
    cone_radius=1.0,
    cone_length=3.0,
    color='purple',
    alpha=1.0,
    n=40
):
    """
    Plots a 3D arrow as a cylinder shaft plus cone head.
    start and end are 3-element arrays/lists.
    """

    start = np.array(start, dtype=float)
    end = np.array(end, dtype=float)

    vector = end - start
    length = np.linalg.norm(vector)

    if length == 0:
        raise ValueError("Arrow length must be nonzero.")

    direction = vector / length

    # Shaft ends before the cone head
    shaft_end = end - cone_length * direction
    shaft_length = np.linalg.norm(shaft_end - start)

    # Create orthonormal basis perpendicular to arrow direction
    arbitrary = np.array([0, 0, 1], dtype=float)

    if np.allclose(direction, arbitrary):
        arbitrary = np.array([0, 1, 0], dtype=float)

    v1 = np.cross(direction, arbitrary)
    v1 = v1 / np.linalg.norm(v1)

    v2 = np.cross(direction, v1)
    v2 = v2 / np.linalg.norm(v2)

    theta_vals = np.linspace(0, 2 * np.pi, n)

    # Cylinder shaft
    z_vals = np.linspace(0, shaft_length, 2)
    theta_grid, z_grid = np.meshgrid(theta_vals, z_vals)

    shaft_points = (
        start[:, None, None]
        + direction[:, None, None] * z_grid[None, :, :]
        + radius * np.cos(theta_grid)[None, :, :] * v1[:, None, None]
        + radius * np.sin(theta_grid)[None, :, :] * v2[:, None, None]
    )

    ax.plot_surface(
        shaft_points[0],
        shaft_points[1],
        shaft_points[2],
        color=color,
        alpha=alpha,
        linewidth=0,
        shade=True
    )

    # Cone head
    cone_z_vals = np.linspace(0, cone_length, 2)
    theta_grid, cone_z_grid = np.meshgrid(theta_vals, cone_z_vals)

    cone_radii = cone_radius * (1 - cone_z_grid / cone_length)

    cone_points = (
        shaft_end[:, None, None]
        + direction[:, None, None] * cone_z_grid[None, :, :]
        + cone_radii[None, :, :] * np.cos(theta_grid)[None, :, :] * v1[:, None, None]
        + cone_radii[None, :, :] * np.sin(theta_grid)[None, :, :] * v2[:, None, None]
    )

    ax.plot_surface(
        cone_points[0],
        cone_points[1],
        cone_points[2],
        color=color,
        alpha=alpha,
        linewidth=0,
        shade=True
    )


# Create figure
fig = plt.figure(figsize=(8, 7))
ax = fig.add_subplot(111, projection='3d')

# Dimensions in cm
x_min, x_max = -15, 15
y_min, y_max = -15, 15
z_min, z_max = 0, 30

# XZ plane vertices, located at y = 0
xz_plane = [
    [x_min, 0, z_min],
    [x_max, 0, z_min],
    [x_max, 0, z_max],
    [x_min, 0, z_max]
]

# Add translucent XZ plane
ax.add_collection3d(
    Poly3DCollection(
        [xz_plane],
        facecolors='#C4E2F3',
        edgecolors='black',
        linewidths=1,
        alpha=0.2
    )
)

# XY plane vertices, located at z = 0
xy_plane = [
    [x_min, y_min, z_min],
    [x_max, y_min, z_min],
    [x_max, y_max, z_min],
    [x_min, y_max, z_min]
]

# # Add translucent XY plane
# ax.add_collection3d(
#     Poly3DCollection(
#         [xy_plane],
#         facecolors='#C4E2F3',
#         edgecolors='0.55',
#         linewidths=0.8,
#         alpha=0.20
#     )
# )

# Draw volume edges
corners = np.array([
    [x_min, y_min, z_min],
    [x_max, y_min, z_min],
    [x_max, y_max, z_min],
    [x_min, y_max, z_min],
    [x_min, y_min, z_max],
    [x_max, y_min, z_max],
    [x_max, y_max, z_max],
    [x_min, y_max, z_max]
])

edges = [
    (0, 1), (1, 2), (2, 3), (3, 0),  # bottom
    (4, 5), (5, 6), (6, 7), (7, 4),  # top
    (0, 4), (1, 5), (2, 6), (3, 7)   # verticals
]

for i, j in edges:
    ax.plot(
        [corners[i, 0], corners[j, 0]],
        [corners[i, 1], corners[j, 1]],
        [corners[i, 2], corners[j, 2]],
        color='gray',
        linewidth=1
    )

# Feed phase center point
feed = (-15, 0, 25)
ax.scatter(*feed, color='maroon', s=60)

ax.text(
    feed[0], feed[1], feed[2] + 1.5,
    f'Feed Phase Center\n({feed[0]}, {feed[1]}, {feed[2]})',
    color='maroon',
    fontsize=12,
    fontweight='bold',
    ha='center'
)

# Beam direction arrow from origin to (15, 0, 25)
origin = np.array([0, 0, 0])
beam_end = np.array([15, 0, 25])

# Slightly lift the plotted arrow above the bottom face
arrow_origin = np.array([0, 0, 0.3])

# Calculate spherical angles using the true vector from the actual origin
true_beam_vector = beam_end - origin
r = np.linalg.norm(true_beam_vector)

# phi: azimuth angle in the xy-plane, measured from +x toward +y
# theta: polar angle measured from +z
phi = np.degrees(np.arctan2(true_beam_vector[1], true_beam_vector[0]))
theta = np.degrees(np.arccos(true_beam_vector[2] / r))

# Plot 3D arrow as cylinder + cone
plot_3d_arrow(
    ax,
    start=arrow_origin,
    end=beam_end,
    radius=0.35,
    cone_radius=1.0,
    cone_length=3.0,
    color='purple',
    alpha=1.0
)

ax.text(
    beam_end[0], beam_end[1], beam_end[2] + 1.5,
    f'Beam Direction\n$\\phi = {phi:.1f}^\\circ$, $\\theta = {theta:.1f}^\\circ$',
    color='purple',
    fontsize=12,
    fontweight='bold',
    ha='center'
)

# Axis limits
ax.set_xlim(x_min, x_max)
ax.set_ylim(y_min, y_max)
ax.set_zlim(z_min, z_max)

# Labels
ax.set_xlabel('X [cm]',
              fontweight = 'bold'
              )
ax.set_ylabel('Y [cm]',
              fontweight = 'bold'
              )
ax.set_zlabel('Z [cm]',
              fontweight = 'bold'
              )

# ax.set_title(
#     'Reflectarray Coordinate System',
#     fontsize=15,
#     fontweight='bold'
# )

# Equal aspect ratio
ax.set_box_aspect((30, 30, 30))

# Trimetric-style view angle
ax.view_init(elev=25, azim=-60)

# Grid
ax.grid(True)

# Grid
ax.grid(True)

# Make grid lines lighter
ax.xaxis._axinfo["grid"]["color"] = (0.8, 0.8, 0.8, 0.4)
ax.yaxis._axinfo["grid"]["color"] = (0.8, 0.8, 0.8, 0.4)
ax.zaxis._axinfo["grid"]["color"] = (0.8, 0.8, 0.8, 0.4)

ax.xaxis._axinfo["grid"]["linewidth"] = 0.8
ax.yaxis._axinfo["grid"]["linewidth"] = 0.8
ax.zaxis._axinfo["grid"]["linewidth"] = 0.8

# Make background panes lighter
ax.xaxis.pane.set_alpha(0.05)
ax.yaxis.pane.set_alpha(0.05)
ax.zaxis.pane.set_alpha(0.05)

plt.tight_layout()
plt.show()