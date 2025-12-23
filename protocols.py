# protocols.py
from models import PatientInput, SimulationState, FluidType, ClinicalDiagnosis

class FluidSelector:
    @staticmethod
    def select_initial_fluid(input: PatientInput, state: SimulationState) -> FluidType:
        if input.hemoglobin_g_dl < 5.0: return FluidType.PRBC
        if input.muac_cm < 11.5 and state.current_glucose_mg_dl < 70: return FluidType.D5_NS
        return FluidType.RL

class PrescriptionEngine:
    @staticmethod
    def generate_bolus(input: PatientInput, fluid: FluidType) -> dict:
        volume = int(input.weight_kg * (10 if input.muac_cm < 11.5 else 20))
        duration = 60 if input.muac_cm < 11.5 else 20
        rate_ml_hr = (volume / duration) * 60
        
        drops_per_ml = input.iv_set_available.value
        drops_per_min = (rate_ml_hr / 60.0) * drops_per_ml
        
        return {
            "volume_ml": volume, "duration_min": duration,
            "rate_ml_hr": int(rate_ml_hr), "drops_per_min": int(drops_per_min)
        }
