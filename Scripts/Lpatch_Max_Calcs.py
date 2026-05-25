# Script to calculate the maximum Lpatch sweep for unit cell (UC) simulation in HFSS.
## The UC consists of a square patch centered within a square ring. The width of the ring remains constant.
# The length of the patch and the gap between the patch ring (Lpatch and g, respectively) are swept. The 
# upper bound for Lpatch for each sweep (Lpatch_max) is a function of g related by the following:
# 
#   Lpatch_max <= L - 2*( d + w )     where L is the length of the unit cell square
#
##

import numpy as np
import unit_convert as uc

Lpatch_max = lambda x,y,z: x - 2*(y+z)
mil_to_mm = lambda x: x/39.37

L = 10
w = 0
Lpatch_min = 1
sweep_steps = 20
mfg_tol = mil_to_mm(8)

g_max = 2 # mm
g_min = 10 # mil

# g = np.linspace( (mil_to_mm(g_min)), g_max, 10)
g = 0


Lpatch_max_vals = Lpatch_max(L, g, w) - ( mfg_tol / 2 )
Lpatch_step = (Lpatch_max_vals - Lpatch_min) / sweep_steps

print(f"g=  {g} \n\n Lpatch_max_vals= {Lpatch_max_vals} \n\n Lpatch_step= {Lpatch_step}")

