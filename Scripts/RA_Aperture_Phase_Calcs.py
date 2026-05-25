import numpy as np
import matplotlib.pyplot as plt

import matplotlib
import matplotlib as mpl

import seaborn as sns
import pandas as pd

import glob as gb
from pathlib import Path

import ezdxf
from ezdxf import units

#################################################
#   DEFINE CONSTANTS    -------------------------
#################################################
c0 = 299792458  # Speed of light
f0 = 10e9       # Center frequency

#################################################
#   REFLECT ARRAY SPECIFICATIONS    -------------
#################################################
feed_x = -15e-2 # Feed center coords (relative to RA center)
feed_y = 0
feed_z = 25e-2

theta0 = np.atan(np.abs(feed_x)/feed_z)
feed_pos = np.array([feed_x, feed_y, feed_z])     # Euclidean coordinates for feed location relative to center of aperture
reflection_dir = np.array([-feed_x, feed_y, feed_z]) / np.linalg.norm(np.array([-feed_x, feed_y, feed_z]))
array_length = 30e-2           # array length = n in an n x n RA
UC_length = 10e-3               # unit cell length in  m
Lambda = c0/f0    # wavelength in m
# print(Lambda)
k0 = (2*np.pi)/Lambda


#################################################
#   READ UC PHASE-TO-LENGTH LOOKUP TABLE    -----
#################################################
# Resolve path to project folder
script_dir = Path(__file__).resolve().parent
lut_path = script_dir / 'UC_lut_simulation_data' / 'RApatchsizes_V1_L2RR_RO4350B.csv'

# Read data from UC phase-to-length lookup table
UC_lut = pd.read_csv(lut_path)
UC_lut_length =  np.array(UC_lut['$Lpatch [mm]'])
UC_lut_phase = np.array(UC_lut['ang_deg(S(FloquetPort1:1,FloquetPort1:1)) [deg]'])


#################################################
#   RA PHASE DISTRIBUTION VS APERTURE CALCS    --
#################################################
Phi_spd = np.zeros((30, 30))
Phi_pp = np.zeros((30, 30))
Ri = np.zeros((30, 30))
Phi_RA = np.zeros((30,30))
for i in range(30):
    for j in range(30):
        UC_pos = np.array([UC_length*(i+1/2)-array_length/2, UC_length*(j+1/2)-array_length/2, 0])  # UC pos vector relative to origin
        # print(UC_pos)
        Ri_hat = UC_pos - feed_pos  # UC position vector relative to feed
        Ri[i][j] = np.linalg.norm(Ri_hat)
        Phi_spd[i][j] = -k0*Ri[i][j]
        Phi_pp[i][j] = -k0*np.dot(UC_pos, reflection_dir)
        Phi_RA[i][j] = k0*(Ri[i][j]-np.sin(theta0)*UC_pos[0])
        
        # Phi_RA[i][j] = -Phi_spd[i][j] + Phi_pp[i][j]

Phi_RA = (Phi_RA + np.pi) % (2 * np.pi) - np.pi        
Phi_RA = Phi_RA
Phi_RA = np.rad2deg(Phi_RA)

Phi_spd = (Phi_spd + np.pi) % (2 * np.pi) - np.pi 
Phi_spd = Phi_spd

#################################################
#   CONVERT RA PHASE DIST TO UC LENGTHS    ------
#################################################
diff = np.abs(Phi_RA[..., None] - UC_lut_phase)
closest_idx = diff.argmin(axis=-1)
size_array = UC_lut_length[closest_idx]

#################################################
#   STORE GENERATED DATA TO CSV    --------------
#################################################

output_folder = script_dir / "RA_Aperture_Patch_and_Phase_Outputs"
output_folder.mkdir(exist_ok=True)   # create folder if it doesn't exist

df = pd.DataFrame(Phi_RA)
df.to_csv(output_folder / "RA_Phase_Distribution_Over_Aperture_reflected_ab.csv", index=False)

df = pd.DataFrame(np.rad2deg(Phi_spd))
df.to_csv(output_folder / "RA_Phase_Distribution_Over_Aperture_broadside_ab.csv", index=False)

df = pd.DataFrame(Ri)
df.to_csv(output_folder / "R_arraycenter.csv", index=False)

df = pd.DataFrame(size_array)
df.to_csv(output_folder / "size_array.csv", index=False)

#################################################
#   GENERATING DXF FILE     ---------------------
#################################################

doc = ezdxf.new(dxfversion="R2010")
doc.units = units.MM
msp = doc.modelspace()

for i in range(30):
    for j in range(30):

        x_in = (i + 0.5) * 10
        y_in = (j + 0.5) * 10
        l = size_array[i][j]/2
    

        # Define the 4 points
        p1 = (x_in - l, y_in - l)
        p2 = (x_in - l, y_in + l)
        p3 = (x_in + l, y_in - l)
        p4 = (x_in + l, y_in + l)

        # Add a SOLID entity
        msp.add_solid([p1, p2, p3, p4])

dxf_file_name = "PCB_30by30_square_10ghz_RO4350B.dxf"
doc.saveas(output_folder / dxf_file_name)
print("DXF file was written: PCB_30by30_square_10ghz.dxf")


#################################################
#   PLOTS FOR PHASE DIST VS APERTURE    ---------
#################################################
fig, axes = plt.subplots(1,2, figsize = (15,15))

sns.heatmap(Phi_RA, ax=axes[0], cmap='viridis', square=True, cbar_kws={'fraction': 0.046, 'pad': 0.04})
sns.heatmap(np.rad2deg(Phi_spd), ax=axes[1], cmap='viridis', square=True, cbar_kws={'fraction': 0.046, 'pad': 0.04})

for x in range(2):

    axes[x].set_xticks([0, 15, 30])  # positions (column indices)
    axes[x].set_yticks([0, 15, 30])  # positions (row indices)

    axes[x].set_xticklabels(['-15', '0', '15'])  # positions (column indices)
    axes[x].set_yticklabels(['-15', '0', '15'])  # positions (row indices)

    axes[x].set_xlabel("UC y-axis position", fontsize=12)
    axes[x].set_ylabel("UC x-axis position", fontsize=12)

axes[0].set_title("Reflected Beam Phase Distribution", fontsize=16, fontweight='bold')
axes[1].set_title("Broadside Beam Phase Distribution", fontsize=16, fontweight='bold')


# print(Phi_RA)
# axes[0].imshow(Phi_RA)
# plt.colorbar()
# plt.tight_layout()
plt.show()

