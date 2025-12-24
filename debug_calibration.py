# debug_calibration.py
from core_physics import PediaFlowPhysicsEngine
from models import PatientInput, ClinicalDiagnosis, CalculationWarnings, OngoingLosses
from constants import FLUID_LIBRARY, FluidType

def run_debug():
    print("\n========================================")
    print("   PEDIAFLOW SAFETY LOGIC DEBUGGER")
    print("========================================")

    # 1. DEFINE THE PROBLEM CASE ("Heart Failure Risk")
    # High RR (60), Low SpO2 (85%), Normal BP (100/65)
    data = {
        "age_months": 60, "weight_kg": 18.0, "sex": "M", "muac_cm": 15.0,
        "height_cm": 110.0, "temp_celsius": 37.0,
        "systolic_bp": 100, "diastolic_bp": 65, 
        "heart_rate": 120, 
        "respiratory_rate_bpm": 60,  # <--- CRITICAL TRIGGER 1
        "sp_o2_percent": 85,         # <--- CRITICAL TRIGGER 2
        "capillary_refill_sec": 2,
        "hemoglobin_g_dl": 12.0, "current_sodium": 135.0,
        "current_glucose": 90.0, "hematocrit_pct": 36.0,
        "diagnosis": undifferentiated_shock,
        "ongoing_losses_severity": OngoingLosses.NONE,
        "illness_day": 1,
        "iv_set_available": 60
    }

    # 2. SETUP
    patient = PatientInput(**data)
    warnings = CalculationWarnings()
    
    print(f"Patient Vitals:")
    print(f" > SpO2: {patient.sp_o2_percent}% (Should trigger Wet Lungs if < 90)")
    print(f" > RR:   {patient.respiratory_rate_bpm} (Should trigger Wet Lungs if > 50)")

    # 3. RUN INITIALIZATION
    print("\n--- CHECKING INITIALIZATION ---")
    params = PediaFlowPhysicsEngine.initialize_physics_engine(patient, warnings)
    state = PediaFlowPhysicsEngine.initialize_simulation_state(patient, params)
    
    print(f" > Initial PCWP:        {state.pcwp_mmHg:.2f} mmHg")
    print(f" > Initial P_Inter:     {state.p_interstitial_mmHg:.2f} mmHg")

    # 4. DIAGNOSIS
    print("\n--- DIAGNOSIS ---")
    if state.pcwp_mmHg >= 15.0 and state.p_interstitial_mmHg >= 4.0:
        print("✅ SUCCESS: Logic triggered. Lungs initialized as 'Wet'.")
    else:
        print("❌ FAILURE: Logic missed. Lungs initialized as 'Dry'.")
        print("   -> The 'if input.sp_o2_percent < 90...' block in initialize_simulation_state is NOT working.")

    # 5. RUN 1 MINUTE SIMULATION
    print("\n--- RUNNING 1 MINUTE OF FLUID ---")
    fluid = FLUID_LIBRARY.get(FluidType.RL)
    # Give a small bolus rate
    next_state = PediaFlowPhysicsEngine.simulate_single_step(state, params, 500.0, FluidType.RL, 1.0)
    
    print(f" > Minute 1 P_Inter:    {next_state.p_interstitial_mmHg:.2f} mmHg")
    if next_state.p_interstitial_mmHg > 5.0:
        print("✅ SUCCESS: Safety Threshold (>5.0) crossed.")
    else:
        print("❌ FAILURE: Still below Safety Threshold.")

if __name__ == "__main__":
    run_debug()



