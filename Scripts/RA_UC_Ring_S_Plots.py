import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import glob

g = 2   # size of gap between patch and ring in mm
w = 0.5 # width microstrip ring in mm

plt.figure()
data = pd.read_csv(r'C:\Users\jjelv\Documents\Thesis_2025\Thesis_Synced_Files\RA_UC_Ring_Raw_Data\1,030mm_Patch+Ring\Square_Patch_1,030mm_g_Ring_S11_Phase_vs_Lpatch_3,6mm_H_10ghz.csv')
plt.plot(data['$Lpatch [mm]'], np.degrees(np.unwrap(np.radians(data['ang_deg(S(FloquetPort1:1,FloquetPort1:1)) [deg]']))))
plt.title("Patch + Ring UC: S11 Phase vs. Patch Length")
plt.xlabel('Patch Length (mm)')
plt.ylabel('Phase (deg)')
plt.xlim(1,7)
plt.show()

