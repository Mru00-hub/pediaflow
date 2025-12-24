# debug_calibration.py
from core_physics import PediaFlowPhysicsEngine
from models import PatientInput, ClinicalDiagnosis, CalculationWarnings, OngoingLosses
from constants import FLUID_LIBRARY, FluidType

def run_debug():
    print("\n========================================")
    print("   PEDIAFLOW DEHYDRATION DEBUGGER")
    print("========================================")

    # 1. DEFINE THE PROBLEM CASE ("Dehydrated Child")
    # Expected BP: 90/60 -> MAP ~70.0
    data = {
        "age_months": 60, "weight_kg": 18.0, "sex": "F", "muac_cm": 15.0,
        "height_cm": 110.0, "temp_celsius": 37.0,
        "systolic_bp": 90, "diastolic_bp": 60, # Target MAP = 70.0
        "heart_rate": 110, "respiratory_rate_bpm": 25,
        "sp_o2_percent": 98, "capillary_refill_sec": 2,
        "hemoglobin_g_dl": 12.0, "current_sodium": 140.0,
        "current_glucose": 90.0, "hematocrit_pct": 36.0,
        "diagnosis": ClinicalDiagnosis.SEVERE_DEHYDRATION, # <--- The Key
        "ongoing_losses_severity": OngoingLosses.NONE,
        "illness_day": 1,
        "iv_set_available": 20
    }

    # 2. SETUP
    patient = PatientInput(**data)
    warnings = CalculationWarnings()
    
    # Calculate expected targets manually to compare
    target_map = 60 + (90 - 60)/3.0
    print(f"\n[GOAL] Target MAP:       {target_map:.2f} mmHg")

    # 3. RUN CALIBRATION (initialize_physics_engine)
    print("\n--- PHASE 1: CALIBRATION ---")
    params = PediaFlowPhysicsEngine.initialize_physics_engine(patient, warnings)
    
    print(f" > Contractility:        {params.cardiac_contractility:.2f} (Should be >1.0 if compensated)")
    print(f" > SVR Resistance:       {params.svr_resistance:.2f}")
    print(f" > Optimal Preload Vol:  {params.optimal_preload_ml:.2f} ml")

    # 4. RUN INITIALIZATION (initialize_simulation_state)
    print("\n--- PHASE 2: INITIALIZATION ---")
    state = PediaFlowPhysicsEngine.initialize_simulation_state(patient, params)
    
    current_blood_ml = state.v_blood_current_l * 1000.0
    print(f" > Actual Blood Vol:     {current_blood_ml:.2f} ml")
    print(f" > Initial CVP:          {state.cvp_mmHg:.2f} mmHg")

    # 5. RUN PHYSICS SNAPSHOT (T=0)
    print("\n--- PHASE 3: PHYSICS ENGINE THINKING (T=0) ---")
    fluid = FLUID_LIBRARY.get(FluidType.RL)
    fluxes = PediaFlowPhysicsEngine._calculate_derivatives(state, params, fluid, 0.0)
    
    # --- MANUAL RE-CALCULATION TO FIND THE BUG ---
    preload_ratio = current_blood_ml / params.optimal_preload_ml
    
    # Check Frank-Starling Logic
    if preload_ratio <= 1.0: efficiency = preload_ratio
    elif preload_ratio <= 1.2: efficiency = 1.0
    else: efficiency = max(0.4, 1.0 - ((preload_ratio - 1.2) * 1.5))

    # Check Afterload Logic
    norm_svr = params.svr_resistance / 1000.0
    denom = 1.0 + (norm_svr - 1.0) * params.afterload_sensitivity
    afterload_factor = 1.0 / max(0.5, denom)
    
    # Calculate CO
    co_l_min = (params.max_cardiac_output_l_min * params.cardiac_contractility * efficiency * afterload_factor)
    
    print(f" 1. Preload Ratio:       {preload_ratio:.3f} (Tank % Full)")
    print(f" 2. FS Efficiency:       {efficiency:.3f} (Pump Efficiency)")
    print(f" 3. Afterload Factor:    {afterload_factor:.3f} (Resistance Penalty)")
    print(f" 4. Cardiac Output:      {co_l_min:.3f} L/min")
    
    derived_map = fluxes['derived_map']
    print(f"\n[RESULT] Engine MAP:     {derived_map:.2f} mmHg")
    print(f"[ERROR]  Difference:     {derived_map - target_map:.2f} mmHg")

    if abs(derived_map - target_map) > 5.0:
        print("\n❌ DIAGNOSIS:")
        if params.cardiac_contractility <= 1.0:
            print("   -> CRITICAL: Contractility is {params.cardiac_contractility}. It needs to be ~1.2-1.4!")
            print("      The 'Adrenaline Surge' logic is missing or not triggering.")
        elif efficiency < 0.6:
            print("   -> ISSUE: The heart is too empty (Low Efficiency). SVR can't fix this alone.")
        elif afterload_factor < 0.5:
             print("   -> ISSUE: The SVR is too high, choking the heart (Afterload Failure).")
    else:
        print("\n✅ SUCCESS: Engine is Calibrated.")

if __name__ == "__main__":
    run_debug()


