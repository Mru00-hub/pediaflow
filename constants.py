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

class FLUID_LIBRARY:
    """
    The Pharmacopoeia of Fluids. 
    Defines how different fluids behave physically.
    """
    SPECS = {
        FluidType.RL: FluidProperties(
            name="Ringer Lactate", 
            sodium_meq_l=130, glucose_g_l=0, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.25 # Crystalloid: 1/4 stays, 3/4 leaks
        ),
        FluidType.NS: FluidProperties(
            name="Normal Saline", 
            sodium_meq_l=154, glucose_g_l=0, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.25
        ),
        FluidType.D5_NS: FluidProperties(
            name="D5 Normal Saline", 
            sodium_meq_l=154, glucose_g_l=50, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.20 # Glucose metabolizes -> free water -> cells
        ),
        FluidType.COLLOID_ALBUMIN: FluidProperties(
            name="Albumin 5%", 
            sodium_meq_l=145, glucose_g_l=0, oncotic_pressure_mmhg=20.0, # High Pull
            vol_distribution_intravascular=1.0, # Stays in vessel
            is_colloid=True
        ),
        FluidType.PRBC: FluidProperties(
            name="Packed Red Blood Cells",
            sodium_meq_l=140, glucose_g_l=0, oncotic_pressure_mmhg=25.0,
            vol_distribution_intravascular=1.0,
            is_colloid=True
        )
    }

    @staticmethod
    def get(fluid_enum: FluidType) -> FluidProperties:
        return FLUID_LIBRARY.SPECS.get(fluid_enum, FLUID_LIBRARY.SPECS[FluidType.RL])
