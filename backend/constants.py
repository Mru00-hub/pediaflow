from enum import Enum
from dataclasses import dataclass
VERSION = "1.0.0"  

class FluidType(Enum):
    RL = "ringer_lactate"
    NS = "normal_saline_0.9"
    D5_NS = "dextrose_5_normal_saline"      # For Hypoglycemia Risk
    RESOMAL = "resomal_rehydration_sol"     # For SAM
    PRBC = "packed_red_blood_cells"         # For Severe Anemia
    COLLOID_ALBUMIN = "albumin_5_percent" # REQUIRED: For Refractory Dengue/Sepsis
    ORS_SOLUTION = "oral_rehydration_solution" # REQUIRED: For bridging IV to Oral
    HALF_NS = "half_normal_saline"
    D5_HALF = "dextrose_5_half_normal_saline"

@dataclass
class FluidProperties:
    name: str
    sodium_meq_l: float
    glucose_g_l: float
    oncotic_pressure_mmhg: float  # The "Pull" force
    vol_distribution_intravascular: float  # How much stays in veins immediately?
    potassium_meq_l: float = 0.0 
    
    # Critical for specific logic
    is_colloid: bool = False
    osmolarity: float = 280.0  # Default to isotonic if not specified

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
            vol_distribution_intravascular=0.25, # Crystalloid: 1/4 stays, 3/4 leaks
            potassium_meq_l=4.0,
            osmolarity=273.0
        ),
        FluidType.NS: FluidProperties(
            name="Normal Saline", 
            sodium_meq_l=154, glucose_g_l=0, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.25,
            potassium_meq_l=0.0,
            osmolarity=308.0
        ),
        FluidType.RESOMAL: FluidProperties(
            name="ReSoMal",
            sodium_meq_l=45, glucose_g_l=25, oncotic_pressure_mmhg=0,
            potassium_meq_l=40.0,
            vol_distribution_intravascular=0.20
        ),
        FluidType.D5_NS: FluidProperties(
            name="D5 Normal Saline", 
            sodium_meq_l=154, glucose_g_l=50, oncotic_pressure_mmhg=0, 
            vol_distribution_intravascular=0.20, # Glucose metabolizes -> free water -> cells
            potassium_meq_l=0.0,
            osmolarity=560.0
        ),
        FluidType.COLLOID_ALBUMIN: FluidProperties(
            name="Albumin 5%", 
            sodium_meq_l=145, glucose_g_l=0, oncotic_pressure_mmhg=20.0, # High Pull
            vol_distribution_intravascular=1.0, # Stays in vessel
            potassium_meq_l=0.0,
            is_colloid=True,
            osmolarity=308.0
        ),
        FluidType.PRBC: FluidProperties(
            name="Packed Red Blood Cells",
            sodium_meq_l=140, glucose_g_l=0, oncotic_pressure_mmhg=25.0,
            vol_distribution_intravascular=1.0,
            potassium_meq_l=4.0, 
            is_colloid=True,
            osmolarity=300.0
        ),
        FluidType.ORS_SOLUTION: FluidProperties(
            name="Oral Rehydration Solution",
            sodium_meq_l=75, glucose_g_l=13.5, oncotic_pressure_mmhg=0,
            vol_distribution_intravascular=0.20,
            potassium_meq_l=20.0
        ),
        FluidType.HALF_NS: FluidProperties(
            name="Half Normal Saline (0.45%)",
            sodium_meq_l=77.0,       # Half of 154
            glucose_g_l=0.0,
            oncotic_pressure_mmhg=0.0,        
            vol_distribution_intravascular=0.15, # Leaves vessels quickly
            potassium_meq_l=0.0,
            is_colloid=False, 
            osmolarity=154.0 # Hypotonic (Dangerous for brain)
        ),
        FluidType.D5_HALF: FluidProperties(
            name="D5 Half NS",
            sodium_meq_l=77.0,
            glucose_g_l=50.0,
            oncotic_pressure_mmhg=0.0,
            vol_distribution_intravascular=0.15,
            potassium_meq_l=0.0,
            osmolarity=432.0
        )
    }

    @staticmethod
    def get(fluid_enum: FluidType) -> FluidProperties:
        return FLUID_LIBRARY.SPECS.get(fluid_enum, FLUID_LIBRARY.SPECS[FluidType.RL])
