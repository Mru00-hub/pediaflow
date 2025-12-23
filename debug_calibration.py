# debug_calibration.py
from core_physics import PediaFlowPhysicsEngine
from models import PatientInput, ClinicalDiagnosis, CalculationWarnings

def run_debug():
    # 1. Define a "Healthy Child" (Expected BP: 100/65 -> MAP ~76.6)
    print("\n--- DEBUGGING INITIALIZATION MATH ---")
    data = {
        "age_months": 60, "weight_kg": 20.0, "sex": "M", "muac_cm": 16.0,
        "height_cm": 110.0, "temp_celsius": 37.0,
        "systolic_bp": 100, "diastolic_bp": 65, # Target MAP = 76.6
        "heart_rate": 90, "respiratory_rate_bpm": 20,
        "sp_o2_percent": 99, "capillary_refill_sec": 1,
        "hemoglobin_g_dl": 12.0, "current_sodium": 140.0,
        "current_glucose": 90.0, "hematocrit_pct": 36.0,
        "diagnosis": ClinicalDiagnosis.UNKNOWN,
        "ongoing_losses_severity": 0, "illness_day": 1,
        "iv_set_available": 20
    }

    # 2. Create Patient & Params
    patient = PatientInput(**data)
    warnings = CalculationWarnings()
    
    print(f"Target MAP (Input): {76.66:.2f} mmHg")

    # 3. Initialize Params (Where SVR Calibration happens)
    params = PediaFlowPhysicsEngine.initialize_physics_engine(patient, warnings)
    print(f"Calibrated SVR:     {params.svr_resistance:.2f}")

    # 4. Initialize State (Where CVP is calculated)
    state = PediaFlowPhysicsEngine.initialize_simulation_state(patient, params)
    print(f"Initial CVP:        {state.cvp_mmHg:.2f} mmHg")

    # 5. RUN THE PHYSICS for T=0
    # We manually call the derivative function to see what the engine *thinks* happens next
    # (Using a dummy fluid since it doesn't matter for T=0 snapshot)
    from constants import FLUID_LIBRARY, FluidType
    fluid = FLUID_LIBRARY.get(FluidType.RL)
    
    fluxes = PediaFlowPhysicsEngine._calculate_derivatives(state, params, fluid, 0.0)
    
    derived_map = fluxes['derived_map']
    
    print("\n--- T=0 SNAPSHOT ---")
    print(f"Engine Calculated MAP: {derived_map:.2f} mmHg")
    print(f"Difference:            {derived_map - 76.66:.2f} mmHg")
    
    # 6. DIAGNOSIS
    if abs(derived_map - 76.66) < 2.0:
        print("\n✅ SUCCESS: Engine is Calibrated.")
    else:
        print("\n❌ FAILURE: Calibration Mismatch.")
        if state.cvp_mmHg != 5.0:
            print("   -> SUSPECT: The Calibration assumed CVP=5.0, but Simulation started with CVP={:.2f}".format(state.cvp_mmHg))

if __name__ == "__main__":
    run_debug()
