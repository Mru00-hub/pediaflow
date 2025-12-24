# debug_calibration.py
from core_physics import PediaFlowPhysicsEngine
from models import PatientInput, CalculationWarnings, OngoingLosses
from constants import FLUID_LIBRARY, FluidType

def run_debug():
    print("\n========================================")
    print("   PEDIAFLOW SAFETY LOGIC DEBUGGER")
    print("========================================")

    # 1. DEFINE THE PROBLEM CASE ("Heart Failure Risk")
    # High RR (60), Low SpO2 (85%)
    data = {
        "age_months": 60, "weight_kg": 18.0, "sex": "M", "muac_cm": 15.0,
        "height_cm": 110.0, "temp_celsius": 37.0,
        "systolic_bp": 100, "diastolic_bp": 65, 
        "heart_rate": 120, 
        "respiratory_rate_bpm": 60,  # <--- CRITICAL TRIGGER
        "sp_o2_percent": 85,         # <--- CRITICAL TRIGGER
        "capillary_refill_sec": 2,
        "hemoglobin_g_dl": 12.0, "current_sodium": 135.0,
        "current_glucose": 90.0, "hematocrit_pct": 36.0,
        "diagnosis": "undifferentiated_shock", 
        "ongoing_losses_severity": OngoingLosses.NONE,
        "illness_day": 1,
        "iv_set_available": 60
    }

    # 2. SETUP
    patient = PatientInput(**data)
    warnings = CalculationWarnings()
    
    # 3. RUN INITIALIZATION
    print("\n--- CHECKING INITIALIZATION ---")
    params = PediaFlowPhysicsEngine.initialize_physics_engine(patient, warnings)
    state = PediaFlowPhysicsEngine.initialize_simulation_state(patient, params)
    
    print(f" > Initial P_Inter:     {state.p_interstitial_mmHg:.2f} mmHg")

    if state.p_interstitial_mmHg < 4.0:
        print("❌ FAILURE: Initial lung pressure is too low. Check initialize_simulation_state logic.")
        return

    # 4. RUN PREDICTION (20 Minutes into the future)
    print("\n--- RUNNING 20-MINUTE PREDICTION ---")
    fluid = FLUID_LIBRARY.get(FluidType.RL)
    
    # Run the full predictive engine
    result = PediaFlowPhysicsEngine.run_simulation(state, params, FluidType.RL, volume_ml=200, duration_min=20)
    
    final_p_inter = result["final_state"].p_interstitial_mmHg
    triggers = result["triggers"]
    
    print(f" > Minute 20 P_Inter:   {final_p_inter:.2f} mmHg")
    print(f" > Safety Triggers:     {triggers}")

    # 5. VERDICT
    if any("Pulmonary Edema" in t for t in triggers):
        print("\n✅ SUCCESS: The engine predicted the flood and STOPPED the infusion.")
    elif final_p_inter > 5.0:
        print("\n✅ SUCCESS: Pressure crossed 5.0 mmHg (Alert should have triggered).")
    else:
        print("\n❌ FAILURE: Pressure did not rise enough. Need to check compliance settings.")

if __name__ == "__main__":
    run_debug()




