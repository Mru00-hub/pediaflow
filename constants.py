from models import FluidType, FluidProperties

class AGE_CONSTANTS:
    # Age (months): (Min RR, Max RR)
    RR_LIMITS = {0: (30,100), 12: (20,80), 60: (15,60), 216: (10,50)}

class PHYSICS_CONSTANTS:
    MINUTES_PER_DAY = 1440.0
    NEONATE_RENAL_MATURITY_BASE = 0.3
    RENAL_MATURATION_RATE_PER_MONTH = 0.029 # (1.0 - 0.3) / 24 months
    
    # Compartment Ratios
    NEONATE_TBW = 0.80
    INFANT_TBW = 0.70
    CHILD_TBW = 0.60
    SAM_HYDRATION_OFFSET = 0.05 # +5% water for SAM
